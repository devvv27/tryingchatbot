from dataclasses import dataclass


@dataclass
class BookingPayload:
    name: str
    email: str
    phone: str
    booking_type: str
    booking_date: str
    booking_time: str
    status: str = "confirmed"
