"""Indian states / union territories and their famous places (ported from src/data/india.ts)."""
import re


def s(name, capital, tagline, places, kind="State"):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("&", "and"))
    return {"name": name, "slug": slug, "capital": capital, "kind": kind, "tagline": tagline, "places": places}


STATES = [
  s("Andhra Pradesh", "Amaravati", "Temples, beaches and spice", ["Tirupati", "Visakhapatnam", "Araku Valley", "Vijayawada", "Srisailam", "Gandikota", "Lepakshi", "Amaravati"]),
  s("Arunachal Pradesh", "Itanagar", "Land of the dawn-lit mountains", ["Tawang", "Ziro Valley", "Bomdila", "Dirang", "Namdapha National Park", "Pasighat", "Itanagar"]),
  s("Assam", "Dispur", "Tea gardens and one-horned rhinos", ["Kaziranga National Park", "Guwahati", "Majuli", "Kamakhya Temple", "Sivasagar", "Manas National Park", "Jorhat"]),
  s("Bihar", "Patna", "Cradle of ancient wisdom", ["Bodh Gaya", "Nalanda", "Rajgir", "Patna", "Vaishali", "Vikramshila"]),
  s("Chhattisgarh", "Raipur", "Waterfalls and tribal heartland", ["Chitrakote Falls", "Raipur", "Bastar", "Sirpur", "Barnawapara Wildlife Sanctuary", "Mainpat"]),
  s("Goa", "Panaji", "Sun, sand and Portuguese charm", ["Baga Beach", "Calangute", "Old Goa", "Palolem Beach", "Dudhsagar Falls", "Anjuna Beach", "Fort Aguada", "Panaji"]),
  s("Gujarat", "Gandhinagar", "Lions, salt deserts and heritage", ["Rann of Kutch", "Gir National Park", "Somnath", "Dwarka", "Ahmedabad", "Statue of Unity", "Saputara", "Rani ki Vav"]),
  s("Haryana", "Chandigarh", "Gateway to the north", ["Kurukshetra", "Gurugram", "Panchkula", "Pinjore Gardens", "Sultanpur National Park", "Morni Hills"]),
  s("Himachal Pradesh", "Shimla", "Snow peaks and apple valleys", ["Manali", "Shimla", "Dharamshala", "Spiti Valley", "Kasol", "Dalhousie", "Kullu", "Bir Billing"]),
  s("Jharkhand", "Ranchi", "Forests and falls", ["Ranchi", "Netarhat", "Betla National Park", "Deoghar", "Hundru Falls", "Jamshedpur"]),
  s("Karnataka", "Bengaluru", "Palaces, coffee and coastline", ["Mysuru", "Hampi", "Coorg", "Bengaluru", "Gokarna", "Chikmagalur", "Badami", "Udupi"]),
  s("Kerala", "Thiruvananthapuram", "God's own country", ["Munnar", "Alleppey", "Kochi", "Wayanad", "Thekkady", "Varkala", "Kovalam", "Kumarakom"]),
  s("Madhya Pradesh", "Bhopal", "The heart of incredible India", ["Khajuraho", "Ujjain", "Bandhavgarh National Park", "Kanha National Park", "Pachmarhi", "Orchha", "Sanchi", "Gwalior"]),
  s("Maharashtra", "Mumbai", "Bollywood, forts and ghats", ["Mumbai", "Pune", "Ajanta Caves", "Ellora Caves", "Lonavala", "Mahabaleshwar", "Shirdi", "Nashik"]),
  s("Manipur", "Imphal", "Jewel of the east", ["Loktak Lake", "Imphal", "Keibul Lamjao National Park", "Ukhrul", "Moirang"]),
  s("Meghalaya", "Shillong", "Abode of the clouds", ["Shillong", "Cherrapunji", "Mawlynnong", "Dawki", "Living Root Bridges", "Mawsynram"]),
  s("Mizoram", "Aizawl", "Rolling blue hills", ["Aizawl", "Champhai", "Reiek", "Vantawng Falls", "Lunglei"]),
  s("Nagaland", "Kohima", "Land of festivals", ["Kohima", "Dzukou Valley", "Mokokchung", "Khonoma", "Dimapur"]),
  s("Odisha", "Bhubaneswar", "Temples and tides", ["Puri", "Konark Sun Temple", "Bhubaneswar", "Chilika Lake", "Simlipal National Park", "Gopalpur"]),
  s("Punjab", "Chandigarh", "Golden temple and warm hearts", ["Amritsar", "Golden Temple", "Wagah Border", "Ludhiana", "Patiala", "Anandpur Sahib"]),
  s("Rajasthan", "Jaipur", "Land of kings", ["Jaipur", "Udaipur", "Jaisalmer", "Jodhpur", "Pushkar", "Mount Abu", "Ranthambore National Park", "Bikaner"]),
  s("Sikkim", "Gangtok", "Himalayan serenity", ["Gangtok", "Tsomgo Lake", "Nathu La", "Pelling", "Lachung", "Yumthang Valley", "Namchi"]),
  s("Tamil Nadu", "Chennai", "Temple towns and hill stations", ["Chennai", "Madurai", "Ooty", "Kodaikanal", "Rameswaram", "Kanyakumari", "Mahabalipuram", "Thanjavur"]),
  s("Telangana", "Hyderabad", "Biryani, pearls and forts", ["Hyderabad", "Charminar", "Golconda Fort", "Warangal", "Ramoji Film City", "Nagarjuna Sagar"]),
  s("Tripura", "Agartala", "Palaces by the lakes", ["Agartala", "Ujjayanta Palace", "Neermahal", "Unakoti", "Jampui Hills"]),
  s("Uttar Pradesh", "Lucknow", "Taj, Ganga and nawabi grace", ["Agra", "Taj Mahal", "Varanasi", "Lucknow", "Mathura", "Vrindavan", "Ayodhya", "Prayagraj"]),
  s("Uttarakhand", "Dehradun", "Devbhoomi, land of gods", ["Rishikesh", "Haridwar", "Nainital", "Mussoorie", "Kedarnath", "Badrinath", "Auli", "Jim Corbett National Park"]),
  s("West Bengal", "Kolkata", "Culture, tea and tigers", ["Kolkata", "Darjeeling", "Sundarbans", "Kalimpong", "Shantiniketan", "Digha"]),
  s("Andaman and Nicobar Islands", "Port Blair", "Turquoise island escape", ["Port Blair", "Havelock Island", "Neil Island", "Radhanagar Beach", "Cellular Jail"], "Union Territory"),
  s("Chandigarh", "Chandigarh", "The planned garden city", ["Rock Garden", "Sukhna Lake", "Rose Garden Chandigarh"], "Union Territory"),
  s("Dadra and Nagar Haveli and Daman and Diu", "Daman", "Quiet coasts and forts", ["Daman", "Diu", "Silvassa"], "Union Territory"),
  s("Delhi", "New Delhi", "Capital of history", ["Red Fort", "Qutub Minar", "India Gate", "Humayun's Tomb", "Chandni Chowk", "Lotus Temple", "Akshardham"], "Union Territory"),
  s("Jammu and Kashmir", "Srinagar", "Paradise on earth", ["Srinagar", "Gulmarg", "Pahalgam", "Sonamarg", "Vaishno Devi", "Dal Lake"], "Union Territory"),
  s("Ladakh", "Leh", "High desert, high passes", ["Leh", "Pangong Lake", "Nubra Valley", "Khardung La", "Tso Moriri", "Kargil"], "Union Territory"),
  s("Lakshadweep", "Kavaratti", "Coral islands", ["Agatti", "Bangaram", "Kavaratti"], "Union Territory"),
  s("Puducherry", "Puducherry", "French quarter by the sea", ["Puducherry", "Auroville", "Paradise Beach", "Promenade Beach"], "Union Territory"),
]

ALL_PLACES = [
    {"place": p, "state": st["name"], "slug": st["slug"]}
    for st in STATES
    for p in st["places"]
]

STATES_BY_SLUG = {st["slug"]: st for st in STATES}
