"""Company facts that live only in the rendered site, not in the catalogue API.

The marketing pages are client-rendered Angular, so these were read off the
live pages rather than fetched as JSON. Treated as a separate, dated block so
it is obvious what came from an API and what was transcribed by hand.

Anything here that the agent will state to a customer — hours, phone numbers,
turnaround claims — should be confirmed with Hindustan Wellness before a
customer-facing pilot.
"""

from __future__ import annotations

VERIFIED_ON = "2026-09-08"
SOURCE = "https://hindustanwellness.com"

SITE_FACTS: dict = {
    "verified_on": VERIFIED_ON,
    "source": SOURCE,
    "company": {
        "name": "Hindustan Wellness",
        "tagline": "Making Hindustan Healthier Each Day",
        "summary": (
            "Diagnostics provider offering blood tests and health checkup "
            "packages with free home sample collection, plus free doctor and "
            "diet consultation after reports."
        ),
        "website": "https://hindustanwellness.com",
    },
    "contact": {
        "phone_primary": "+91 9810981073",
        "phone_alternate": "+91 9810981083",
        "email": "customer.service@hindustanwellness.com",
        "whatsapp": "https://wa.me/message/RQBDHFLFCAIRI1",
        "support_hours": (
            "5:00 AM to 12:00 PM (Mon-Sat); 8:00 AM to 6:00 PM (Sunday & Holidays)"
        ),
        "support_hours_note": (
            "Transcribed as printed on the contact page. The Mon-Sat window reads "
            "'5a.m. to 12p.m.' on site — confirm with the client whether this means "
            "midday or midnight before the agent quotes it."
        ),
    },
    "offices": [
        {
            "city": "New Delhi",
            "address": "17, Block F, Preet Vihar, Delhi, 110092",
        },
        {
            "city": "Gurugram",
            "address": "107, 1st Floor, near LIC Office, Sector 44, Gurugram, Haryana 122001",
        },
        {
            "city": "Bhopal",
            "address": "491, Sector-9/A Saket Nagar, Habib Ganj, Bhopal, Madhya Pradesh 462024",
        },
    ],
    "why_choose_us": [
        "Smart report in 24 hours*",
        "Most affordable pricing",
        "World class lab",
        "Free doctor & diet consultation",
        "On-time sample collection",
        "Presence in 50+ cities",
    ],
    "lab_credentials": [
        "USA-FDA approved fully automatic analysers",
        "Fully barcoded process",
        "Reliable & accurate reports",
        "Free home sample collection",
    ],
    "stats": {
        "tests_performed": "5 Crore+",
        "customers": "50 Lakh+",
        "consultations": "50 Lakh+",
        "cities": "50+",
        "google_rating": "4.6",
        "google_reviews": "17K+",
    },
    "doctors": [
        {"name": "Dr. K. K. Taneja", "credentials": "Ex. Principal Scientist, 40+ yrs experience"},
        {"name": "Dr. Komal Kapoor", "credentials": "MBBS, DNB, 10+ yrs experience"},
        {"name": "Dr. Deepthy Sahadevan", "credentials": "MBBS, MD, 20+ yrs experience"},
        {"name": "Dr. Deepika Chatterjee", "credentials": "MBBS, MD, 20 yrs experience"},
        {"name": "Dr. Sonal Mehrotra", "credentials": "MBBS, MD, 10+ yrs experience"},
        {"name": "Dr. Rajiv Tiwari", "credentials": "MBBS, MD, 20+ yrs experience"},
    ],
    "apps": {
        "ios": "https://apps.apple.com/in/app/hindustan-wellness/id1173476686",
        "android": "https://play.google.com/store/apps/details?id=com.hw.health",
        "features": [
            "View digital reports",
            "Health trends & analysis",
            "Track family member's health",
            "View diet plans & doctor prescriptions",
        ],
    },
    "pages": {
        "faq": "https://hindustanwellness.com/faq",
        "contact": "https://hindustanwellness.com/contact",
        "about_us": "https://hindustanwellness.com/about-us",
        "our_labs": "https://hindustanwellness.com/our-labs",
        "careers": "https://hindustanwellness.com/career",
        "blog": "https://hindustanwellness.com/blog",
        "partner_with_us": "https://hindustanwellness.com/partner-with-us",
        "for_corporate": "https://hindustanwellness.com/for-corporate",
        "for_doctor": "https://hindustanwellness.com/for-doctor",
        "terms": "https://hindustanwellness.com/terms-and-conditions",
    },
    "social": {
        "facebook": "https://www.facebook.com/HindustanWellness",
        "linkedin": "https://www.linkedin.com/company/hindustan-wellness",
        "youtube": "https://www.youtube.com/c/HindustanWellnessOfficial",
        "twitter": "https://www.twitter.com/HindustanHealth",
        "instagram": "https://instagram.com/hindustan_wellness",
    },
    "about": {
        "founded": "2013",
        "team": "Grew from 5 to 500 people",
        "lab": (
            "Own fully automated lab spread across 10,000 sq. ft. with capacity to "
            "process 10,000 samples a day; barcoded and bi-directionally interfaced "
            "systems, instruments from leading international brands."
        ),
        "reach": "28 cities, 35+ districts, over 60,000+ sq. km covered",
        "reach_note": (
            "The About page says 28 cities while the home page badge says 'Presence in "
            "50+ Cities'. Conflicting — confirm the correct figure with the client "
            "before the agent quotes coverage."
        ),
    },
    # Booking, report delivery and package-change rules — the operational core of
    # the help desk. Captured from the FAQ accordion, which loads answers on click.
    "faqs": [
        {
            "question": "What is the core business of Hindustan Wellness?",
            "answer": (
                "Making quality healthcare accessible to everyone through preventative "
                "health services, delivering health solutions with convenience and "
                "affordability."
            ),
        },
        {
            "question": "What are the benefits?",
            "answer": (
                "Packaged solutions for specific preventive healthcare needs, free Doctor "
                "and Dietician consultations, an extensive network of healthcare "
                "professionals, a dedicated health manager, and home collection service."
            ),
        },
        {
            "question": "How does the system work?",
            "answer": (
                "Select a package via one of 4 channels - Call, WhatsApp chat, mobile app "
                "or website. Book it, provide contact details, and arrange the sample "
                "collection date and time at checkout. After testing, reports are "
                "delivered by SMS, email and WhatsApp. A doctor then calls to discuss the "
                "report, or you can consult a doctor over video in the Hindustan Wellness "
                "app. Dietician and health manager consultations are also free."
            ),
        },
        {
            "question": "How do I know the best package for my needs?",
            "answer": (
                "There are pre-constituted packages covering a broad range of needs. If "
                "none fits, call 9810981073 or reach the same number on WhatsApp."
            ),
        },
        {
            "question": "How do I manage my package?",
            "answer": (
                "Every customer is assigned a health manager. Call 9810981073 and ask to "
                "speak with your health manager."
            ),
        },
        {
            "question": "Can I modify a package?",
            "answer": (
                "Yes - either before sample pickup by contacting us on call or WhatsApp "
                "(9810981073), or by asking the sample collection officer at pickup."
            ),
        },
        {
            "question": "What if I need a specific test?",
            "answer": (
                "The process is the same as booking a health package, via any of the 4 "
                "channels - Call, WhatsApp chat, mobile app or website."
            ),
        },
    ],
    "booking_channels": ["Call", "WhatsApp chat", "Mobile app", "Website"],
    "report_delivery": ["SMS", "Email", "WhatsApp", "Mobile app"],
    "package_url_template": "https://hindustanwellness.com/package/{slug}",
}
