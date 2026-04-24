import requests
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("API_KEY")


def nearby_search(location, radius, place_type):
    """
    Fetches only the first page of results (max 20 places).
    Pagination is intentionally removed to stay within Vercel's
    free-tier 10-second function execution limit.
    """
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": location,
        "radius": radius,
        "type": place_type,
        "key": API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data.get("results", [])


def get_website_and_phone(place_id):
    """
    Fetches only website and phone from the Details API.
    All other fields (name, rating, reviews, address) are taken
    directly from the nearby search response to minimize per-call
    payload and latency.
    """
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "website,formatted_phone_number",
        "key": API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    result = data.get("result", {})
    return place_id, result.get("website"), result.get("formatted_phone_number", "N/A")


def get_coordinate(place_name):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": place_name,
        "key": API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()

    if data.get("results"):
        location = data["results"][0]["geometry"]["location"]
        return f"{location['lat']},{location['lng']}"
    return None


def calculate_urgency(business):
    score = 0
    reasons = []

    reviews = business.get("reviews", 0)
    if reviews > 1000:
        score += 40
        reasons.append(f"very popular ({reviews} reviews)")
    elif reviews > 200:
        score += 30
        reasons.append(f"popular ({reviews} reviews)")
    elif reviews > 50:
        score += 20
        reasons.append(f"moderate reviews ({reviews})")
    elif reviews > 10:
        score += 10
        reasons.append(f"some reviews ({reviews})")

    rating = business.get("rating", 0)
    if rating >= 4.5:
        score += 30
        reasons.append(f"excellent rating ({rating})")
    elif rating >= 4.0:
        score += 20
        reasons.append(f"good rating ({rating})")
    elif rating >= 3.5:
        score += 10
        reasons.append(f"average rating ({rating})")

    if business.get("phone") not in ("N/A", None, ""):
        score += 10
        reasons.append("has phone number")

    high_priority_types = [
        "doctor", "lawyer", "dentist", "hospital",
        "hotel", "real_estate_agency", "accounting"
    ]
    medium_priority_types = [
        "restaurant", "gym", "beauty_salon",
        "hair_care", "spa", "school"
    ]

    business_type = business.get("type", "")
    if business_type in high_priority_types:
        score += 20
        reasons.append(f"high trust category ({business_type})")
    elif business_type in medium_priority_types:
        score += 10
        reasons.append(f"medium priority category ({business_type})")

    if score >= 80:
        label = "URGENT"
    elif score >= 50:
        label = "MEDIUM"
    else:
        label = "LOW"

    return {
        "score": score,
        "label": label,
        "reasons": ", ".join(reasons) if reasons else "no signals detected"
    }


def find_no_website(location, radius, place_type):
    places = nearby_search(location, radius, place_type)

    # Concurrently fetch only website + phone for each place.
    # With max 20 places and max_workers=10, two batches of 10
    # parallel requests complete in roughly 2-4 seconds total,
    # well within the 10-second Vercel free-tier limit.
    details_map = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(get_website_and_phone, place["place_id"]): place
            for place in places
        }
        for future in as_completed(futures):
            try:
                place_id, website, phone = future.result()
                details_map[place_id] = {"website": website, "phone": phone}
            except Exception:
                pass

    no_website = []

    for place in places:
        place_id = place["place_id"]
        detail = details_map.get(place_id, {})

        if detail.get("website"):
            continue

        # Name, rating, reviews, and vicinity come from the nearby
        # search response directly — no extra API call needed.
        business = {
            "name":     place.get("name", "N/A"),
            "phone":    detail.get("phone", "N/A"),
            "rating":   place.get("rating", 0),
            "reviews":  place.get("user_ratings_total", 0),
            "address":  place.get("vicinity", "N/A"),
            "type":     place_type,
            "maps_link": (
                f"https://www.google.com/maps/search/?api=1"
                f"&query=Google&query_place_id={place_id}"
            )
        }

        urgency = calculate_urgency(business)
        business.update(urgency)
        no_website.append(business)

    return no_website
