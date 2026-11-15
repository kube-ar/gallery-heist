"""The precinct's full tool catalog (detective 5): the desk's tools, and many more that aren't
about tonight. Each tool says what kind of thing it takes and what kind it gives back, so tools
can be chained by type, and which class of action it is.

    machine     reads; the agent may run it alone
    supervised  changes a case's outcome; needs evidence from logs, not only from statements
    human       never the agent's call
"""

from __future__ import annotations

# name: (description, takes, gives, class)
CATALOG: dict[str, tuple[str, str, str, str]] = {
    "briefing": ("What the night shift reported about the theft.", "Case", "Report", "machine"),
    "rulebook": ("The chief's rules for a warrant.", "Case", "Rule", "machine"),
    "list_people": ("Everyone on the museum's lists: staff, guests and contract workers, with ids and roles.", "Case", "Person", "machine"),
    "floor_plan": ("The rooms of each wing and the doors between them, with card readers.", "Wing", "Room", "machine"),
    "documents": ("Reports, emails and press filed tonight.", "Case", "Document", "machine"),
    "read_document": ("The text of one document.", "Document", "Text", "machine"),
    "keycard_log": ("Badge swipes at the doors of a room: who went in and when.", "Room", "Person", "machine"),
    "camera_log": ("When each security camera went offline or came back online.", "Time", "Camera", "machine"),
    "phone_records": ("Calls made to and from one person's phone.", "Person", "Call", "machine"),
    "bank_records": ("Money transferred in and out of one person's accounts.", "Person", "Account", "machine"),
    "interview": ("One person's statement about the night.", "Person", "Statement", "machine"),
    "accuse": ("Ask the chief for a warrant against a culprit and an accomplice.", "Person", "Warrant", "supervised"),
    # Real tools of a precinct, not about tonight.
    "parking_log": ("Cars entering and leaving the staff car park.", "Time", "Vehicle", "machine"),
    "weather_report": ("The weather in the city by hour.", "Time", "Weather", "machine"),
    "gift_shop_sales": ("Sales at the museum's gift shop by day.", "Time", "Sale", "machine"),
    "cloakroom_tickets": ("Coat-check tickets issued at the cloakroom.", "Time", "Ticket", "machine"),
    "fire_alarm_log": ("Tests and faults of the fire alarm panels.", "Time", "Alarm", "machine"),
    "elevator_log": ("Elevator calls by floor.", "Time", "Elevator", "machine"),
    "wifi_logins": ("Devices that joined the guest wifi.", "Time", "Device", "machine"),
    "catering_orders": ("Food and drink ordered from the caterer.", "Time", "Order", "machine"),
    "insurance_policy": ("The museum's insurance cover for its collection.", "Artwork", "Policy", "machine"),
    "artwork_provenance": ("Where an artwork came from and who owned it before.", "Artwork", "Owner", "machine"),
    "loan_agreements": ("Artworks lent to or borrowed from other museums.", "Artwork", "Loan", "machine"),
    "conservation_reports": ("The condition of an artwork at its last inspection.", "Artwork", "Report", "machine"),
    "visitor_numbers": ("Daily visitor counts.", "Time", "Count", "machine"),
    "ticket_sales": ("Tickets sold online and at the door.", "Time", "Sale", "machine"),
    "membership_list": ("Members of the museum's friends' association.", "Case", "Member", "machine"),
    "donor_pledges": ("Pledges made by donors this year.", "Person", "Pledge", "machine"),
    "press_contacts": ("Journalists who cover the museum.", "Case", "Contact", "machine"),
    "staff_rota": ("Who was scheduled to work which shift.", "Time", "Shift", "machine"),
    "payroll": ("Salaries paid to staff.", "Person", "Payment", "machine"),
    "training_records": ("Courses staff have completed.", "Person", "Course", "machine"),
    "maintenance_tickets": ("Repairs requested by facilities.", "Room", "Ticket", "machine"),
    "lost_and_found": ("Items handed in to the front desk.", "Time", "Item", "machine"),
    "delivery_log": ("Deliveries received at the loading dock.", "Time", "Delivery", "machine"),
    "taxi_bookings": ("Taxis booked by the front desk for guests.", "Time", "Booking", "machine"),
    "social_media_posts": ("Public posts that mention the museum.", "Time", "Post", "machine"),
    "exhibition_schedule": ("Upcoming exhibitions and their rooms.", "Room", "Exhibition", "machine"),
    "light_sensor_log": ("Light levels in the galleries, for conservation.", "Room", "Reading", "machine"),
    "humidity_log": ("Humidity in the galleries and the vault.", "Room", "Reading", "machine"),
    "power_usage": ("Electricity use by wing.", "Wing", "Reading", "machine"),
    "audio_guide_rentals": ("Audio guides lent to visitors.", "Time", "Rental", "machine"),
    "volunteer_list": ("Volunteers and the days they help.", "Case", "Volunteer", "machine"),
    "board_minutes": ("Minutes of the board's meetings.", "Case", "Document", "machine"),
    "budget_report": ("The museum's budget this year.", "Case", "Document", "machine"),
    "vendor_contracts": ("Contracts with caterers, cleaners and AV companies.", "Case", "Contract", "machine"),
    "email_archive": ("Emails sent by one member of staff.", "Person", "Document", "machine"),
    "criminal_records": ("Past convictions of one person.", "Person", "Record", "machine"),
    "vehicle_registrations": ("Who owns a vehicle.", "Vehicle", "Person", "machine"),
    "device_owners": ("Who owns a device seen on the wifi.", "Device", "Person", "machine"),
    "court_calendar": ("Hearings scheduled at the courthouse.", "Time", "Hearing", "machine"),
    "evidence_locker": ("Items held as evidence in a case.", "Case", "Item", "machine"),
    "patrol_routes": ("The routes guards are assigned to walk.", "Wing", "Room", "machine"),
    "lock_inventory": ("Which locks and readers each door has.", "Room", "Door", "machine"),
    # Actions with consequences.
    "freeze_account": ("Freeze one person's bank account.", "Person", "Order", "supervised"),
    "issue_search_warrant": ("Search one person's home.", "Person", "Warrant", "human"),
    "release_suspect": ("Release a person held for questioning.", "Person", "Order", "human"),
    "delete_record": ("Remove a record from the case file.", "Document", "Order", "human"),
    "contact_press": ("Send a statement to the press.", "Document", "Post", "human"),
}  # fmt: skip


def tool_descriptions() -> dict[str, str]:
    return {name: spec[0] for name, spec in CATALOG.items()}
