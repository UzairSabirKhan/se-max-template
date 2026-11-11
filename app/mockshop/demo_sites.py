# ruff: noqa: E501  (data tables: one row per item reads best)
"""More demo sites for showing other use cases: property listings, a scholarship board and a job board.

Everything is INVENTED (names, prices, providers, companies) and served by our own app, like the mock
shop: no real site is copied or scraped. An admin page changes them live during a demo: a property's
price drops, a new scholarship or a new job appears. A restart puts them back to their starting state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from decimal import Decimal

PER_PAGE = 6


@dataclass
class Listing:
    slug: str
    title: str
    price: Decimal          # PKR
    city: str
    area: str
    beds: int
    kind: str


@dataclass
class Scholarship:
    slug: str
    name: str
    provider: str
    amount: Decimal         # PKR per year
    covers: str
    level: str
    deadline: str           # "15 Dec 2026"


@dataclass
class Job:
    slug: str
    title: str
    company: str
    city: str
    salary: Decimal         # PKR per month
    posted: str             # "10 Nov 2026"


LISTINGS = [
    Listing("dha-house-10-marla", "10 Marla House, Sector C", Decimal(25_000_000), "Lahore", "10 Marla", 4, "House"),
    Listing("bahria-flat-2-bed", "2 Bed Apartment, Tower 4", Decimal(9_500_000), "Rawalpindi", "1,050 sq ft", 2, "Flat"),
    Listing("f11-plot-1-kanal", "1 Kanal Residential Plot", Decimal(78_000_000), "Islamabad", "1 Kanal", 0, "Plot"),
    Listing("gulberg-house-5-marla", "5 Marla House near Park", Decimal(14_500_000), "Lahore", "5 Marla", 3, "House"),
    Listing("clifton-flat-3-bed", "3 Bed Sea-View Apartment", Decimal(42_000_000), "Karachi", "1,800 sq ft", 3, "Flat"),
    Listing("g13-house-7-marla", "7 Marla Corner House", Decimal(31_000_000), "Islamabad", "7 Marla", 5, "House"),
    Listing("johar-town-shop", "Ground Floor Shop", Decimal(18_000_000), "Lahore", "400 sq ft", 0, "Shop"),
    Listing("peshawar-plot-10-marla", "10 Marla Plot, Phase 2", Decimal(11_000_000), "Peshawar", "10 Marla", 0, "Plot"),
    Listing("e11-flat-1-bed", "1 Bed Studio Apartment", Decimal(6_800_000), "Islamabad", "620 sq ft", 1, "Flat"),
    Listing("multan-house-8-marla", "8 Marla Double Storey", Decimal(19_500_000), "Multan", "8 Marla", 4, "House"),
    Listing("faisalabad-farmhouse", "4 Kanal Farmhouse", Decimal(56_000_000), "Faisalabad", "4 Kanal", 3, "Farmhouse"),
    Listing("korangi-office", "Office Floor, 2nd Floor", Decimal(23_000_000), "Karachi", "2,200 sq ft", 0, "Office"),
]

SCHOLARSHIPS = [
    Scholarship("future-coders-merit", "Future Coders Merit Scholarship", "Northern Tech Foundation",
                Decimal(150_000), "Tuition", "Undergraduate", "15 Dec 2026"),
    Scholarship("women-in-stem", "Women in STEM Award", "Indus Learning Trust", Decimal(200_000),
                "Tuition and books", "Undergraduate", "31 Dec 2026"),
    Scholarship("need-based-grant", "Need-Based Study Grant", "Margalla Education Fund", Decimal(120_000),
                "Tuition", "Intermediate", "20 Jan 2027"),
    Scholarship("masters-research", "Masters Research Fellowship", "Karakoram Research Council", Decimal(480_000),
                "Full tuition and stipend", "Masters", "10 Feb 2027"),
    Scholarship("sports-excellence", "Sports Excellence Scholarship", "Ravi Sports Academy", Decimal(90_000),
                "Half tuition", "Undergraduate", "5 Jan 2027"),
]
NEW_SCHOLARSHIPS = [
    Scholarship("ai-innovators", "AI Innovators Scholarship", "Chenab Digital Trust", Decimal(250_000),
                "Tuition and laptop", "Undergraduate", "28 Feb 2027"),
    Scholarship("phd-climate", "Climate Research PhD Award", "Green Valley Institute", Decimal(900_000),
                "Full funding", "PhD", "15 Mar 2027"),
]

JOBS = [
    Job("junior-python-dev", "Junior Python Developer", "Saffron Software", "Islamabad", Decimal(120_000), "8 Nov 2026"),
    Job("frontend-react", "Frontend Developer (React)", "Kite Labs", "Lahore", Decimal(150_000), "7 Nov 2026"),
    Job("data-analyst", "Data Analyst", "Blue Pine Analytics", "Karachi", Decimal(140_000), "9 Nov 2026"),
    Job("qa-engineer", "QA Engineer", "Saffron Software", "Islamabad", Decimal(110_000), "6 Nov 2026"),
    Job("devops-intern", "DevOps Intern", "Cedar Cloud", "Rawalpindi", Decimal(45_000), "9 Nov 2026"),
    Job("ui-designer", "UI/UX Designer", "Kite Labs", "Lahore", Decimal(130_000), "5 Nov 2026"),
]
NEW_JOBS = [
    Job("ml-engineer", "Machine Learning Engineer", "Blue Pine Analytics", "Islamabad", Decimal(260_000), "10 Nov 2026"),
    Job("backend-go", "Backend Developer (Go)", "Cedar Cloud", "Karachi", Decimal(210_000), "10 Nov 2026"),
]


@dataclass
class DemoState:
    listings: list[Listing] = field(default_factory=lambda: copy.deepcopy(LISTINGS))
    scholarships: list[Scholarship] = field(default_factory=lambda: copy.deepcopy(SCHOLARSHIPS))
    jobs: list[Job] = field(default_factory=lambda: copy.deepcopy(JOBS))

    def drop_price(self, slug: str, pct: int = 10) -> bool:
        listing = next((x for x in self.listings if x.slug == slug), None)
        if listing is None:
            return False
        listing.price = (listing.price * (100 - pct) / 100).quantize(Decimal(1))
        return True

    def add_scholarship(self) -> bool:
        have = {s.slug for s in self.scholarships}
        new = next((s for s in NEW_SCHOLARSHIPS if s.slug not in have), None)
        if new:
            self.scholarships.insert(0, copy.deepcopy(new))
        return new is not None

    def add_job(self) -> bool:
        have = {j.slug for j in self.jobs}
        new = next((j for j in NEW_JOBS if j.slug not in have), None)
        if new:
            self.jobs.insert(0, copy.deepcopy(new))
        return new is not None

    def reset(self) -> None:
        fresh = DemoState()
        self.listings, self.scholarships, self.jobs = fresh.listings, fresh.scholarships, fresh.jobs


demo_state = DemoState()


def pkr(amount: Decimal) -> str:
    """PKR 25,000,000 (a full number, so it parses as a price)."""
    return f"PKR {int(amount):,}"


def crore(amount: Decimal) -> str:
    """The way property ads also show it: 2.5 Crore / 95 Lakh (display only)."""
    value = Decimal(amount)
    if value >= 10_000_000:
        return f"{(value / 10_000_000).normalize():f} Crore"
    return f"{(value / 100_000).normalize():f} Lakh"
