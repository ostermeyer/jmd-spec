"""Simulated Employee Directory API with rich, schema-testable types.

Designed for Phase 6c Schema-Roundtrip benchmark:
- Enums (department, level)
- Nested objects (address)
- Arrays of primitives (skills)
- Arrays of objects (projects)
- Nullable/optional fields (manager_id, phone)
- Numeric ranges (salary)
- Date format (start_date)
- Email pattern (email)
- Boolean (active)
"""

from __future__ import annotations

from benchmark.simulated_apis.base import SimulatedAPI

# ── Pools for deterministic generation ─────────────────────────────────────

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Eva", "Frank", "Grace", "Henry",
    "Irene", "Jack", "Karen", "Leo", "Mona", "Nick", "Olivia", "Paul",
    "Quinn", "Rita", "Sam", "Tina", "Uwe", "Vera", "Walter", "Xena",
]

LAST_NAMES = [
    "Müller", "Schmidt", "Chen", "Patel", "Garcia", "Johnson", "Kim",
    "Novak", "Santos", "Kowalski", "Dubois", "Tanaka", "Rossi", "Berg",
    "Silva", "Larsen", "Andersson", "Hoffman", "Ali", "Nguyen",
]

DEPARTMENTS = ["Engineering", "Sales", "Marketing", "HR", "Finance", "Operations"]
LEVELS = ["Junior", "Mid", "Senior", "Lead", "Principal"]

SKILLS_POOL = [
    "Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "SQL",
    "React", "Vue", "Docker", "Kubernetes", "AWS", "GCP", "Azure",
    "PostgreSQL", "Redis", "GraphQL", "REST", "CI/CD", "Terraform",
    "Machine Learning", "Data Analysis", "Project Management", "Scrum",
]

PROJECT_NAMES = [
    "Atlas", "Beacon", "Catalyst", "Delta", "Eclipse", "Forge",
    "Gateway", "Horizon", "Insight", "Keystone", "Lighthouse", "Mosaic",
]

PROJECT_ROLES = ["Lead", "Contributor", "Reviewer", "Architect", "Tester"]

STREETS = [
    "Hauptstraße 12", "Berliner Allee 45", "Ringweg 7", "Am Markt 3",
    "Industriestraße 88", "Gartenweg 21", "Bahnhofstraße 5", "Lindenplatz 14",
]

CITIES = [
    ("Berlin", "10115", "DE"), ("München", "80331", "DE"),
    ("Hamburg", "20095", "DE"), ("Köln", "50667", "DE"),
    ("Wien", "1010", "AT"), ("Zürich", "8001", "CH"),
    ("Amsterdam", "1012", "NL"), ("Paris", "75001", "FR"),
]

SALARY_RANGES = {
    "Junior": (35000, 55000),
    "Mid": (50000, 80000),
    "Senior": (75000, 120000),
    "Lead": (100000, 160000),
    "Principal": (140000, 220000),
}


class EmployeeDirectoryAPI(SimulatedAPI):
    """Deterministic employee directory with rich types for schema testing."""

    def __init__(self) -> None:
        super().__init__()
        self.employees: list[dict] = []
        self._generate_data()

    def _generate_data(self) -> None:
        """Generate 10 employees with diverse field types."""
        self.employees = []

        for i in range(10):
            first = self._rng.choice(FIRST_NAMES)
            last = self._rng.choice(LAST_NAMES)
            dept = self._rng.choice(DEPARTMENTS)
            level = self._rng.choice(LEVELS)
            sal_min, sal_max = SALARY_RANGES[level]
            salary = round(self._rng.uniform(sal_min, sal_max), 2)

            street = self._rng.choice(STREETS)
            city, zip_code, country = self._rng.choice(CITIES)

            n_skills = self._rng.randint(2, 5)
            skills = self._rng.sample(SKILLS_POOL, n_skills)

            n_projects = self._rng.randint(1, 3)
            projects = []
            for _ in range(n_projects):
                projects.append({
                    "name": self._rng.choice(PROJECT_NAMES),
                    "role": self._rng.choice(PROJECT_ROLES),
                    "hours_per_week": self._rng.randint(5, 40),
                })

            # manager_id: null for first 2 employees (top-level), otherwise random earlier ID
            manager_id = None
            if i >= 2:
                manager_id = self._rng.randint(1, i)

            # phone: ~30% chance of being null
            phone = None
            if self._rng.random() > 0.3:
                phone = f"+49 {self._rng.randint(100, 999)} {self._rng.randint(1000000, 9999999)}"

            year = self._rng.randint(2018, 2025)
            month = self._rng.randint(1, 12)
            day = self._rng.randint(1, 28)

            employee = {
                "id": i + 1,
                "name": f"{first} {last}",
                "email": f"{first.lower()}.{last.lower()}@example.com",
                "department": dept,
                "role": self._rng.choice([
                    "Software Engineer", "Product Manager", "Data Analyst",
                    "DevOps Engineer", "UX Designer", "QA Engineer",
                    "Technical Writer", "Solutions Architect",
                ]),
                "level": level,
                "salary": salary,
                "currency": self._rng.choice(["EUR", "USD"]),
                "start_date": f"{year:04d}-{month:02d}-{day:02d}",
                "active": self._rng.random() > 0.15,  # ~85% active
                "skills": skills,
                "address": {
                    "street": street,
                    "city": city,
                    "zip": zip_code,
                    "country": country,
                },
                "projects": projects,
                "manager_id": manager_id,
                "phone": phone,
            }
            self.employees.append(employee)

    def get_employees(self) -> list[dict]:
        """Return all employees."""
        return self.employees

    def render_jmd(self) -> str:
        """Render employees as JMD data document."""
        lines = ["# EmployeeDirectory"]
        lines.append(f"count: {len(self.employees)}")
        lines.append(f"generated: true")
        lines.append("")
        lines.append("## employees[]")

        for emp in self.employees:
            lines.append(f"- id: {emp['id']}")
            lines.append(f"  name: {emp['name']}")
            lines.append(f"  email: {emp['email']}")
            lines.append(f"  department: {emp['department']}")
            lines.append(f"  role: {emp['role']}")
            lines.append(f"  level: {emp['level']}")
            lines.append(f"  salary: {emp['salary']}")
            lines.append(f"  currency: {emp['currency']}")
            lines.append(f"  start_date: {emp['start_date']}")
            lines.append(f"  active: {str(emp['active']).lower()}")
            lines.append(f"  ### skills[]")
            for skill in emp['skills']:
                lines.append(f"  - {skill}")
            lines.append(f"  ### address")
            lines.append(f"    street: {emp['address']['street']}")
            lines.append(f"    city: {emp['address']['city']}")
            lines.append(f"    zip: {emp['address']['zip']}")
            lines.append(f"    country: {emp['address']['country']}")
            lines.append(f"  ### projects[]")
            for proj in emp['projects']:
                lines.append(f"  - name: {proj['name']}")
                lines.append(f"    role: {proj['role']}")
                lines.append(f"    hours_per_week: {proj['hours_per_week']}")
            if emp['manager_id'] is not None:
                lines.append(f"  manager_id: {emp['manager_id']}")
            else:
                lines.append(f"  manager_id: null")
            if emp['phone'] is not None:
                lines.append(f"  phone: {emp['phone']}")
            else:
                lines.append(f"  phone: null")

        return "\n".join(lines)

    def render_json(self) -> str:
        """Render employees as pretty-printed JSON."""
        import json
        data = {
            "employee_directory": {
                "count": len(self.employees),
                "generated": True,
                "employees": self.employees,
            }
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def get_ground_truth_schema(self) -> dict:
        """Return the expected schema structure for validation.

        This is NOT given to the LLM — it's used to evaluate
        whether the LLM-derived schema is correct.
        """
        return {
            "root_label": "EmployeeDirectory",
            "fields": {
                "count": {"type": "integer"},
                "generated": {"type": "boolean"},
            },
            "arrays": {
                "employees": {
                    "item_fields": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "department": {
                            "type": "enum",
                            "values": set(DEPARTMENTS),
                        },
                        "role": {"type": "string"},
                        "level": {
                            "type": "enum",
                            "values": set(LEVELS),
                        },
                        "salary": {"type": "number"},
                        "currency": {
                            "type": "enum",
                            "values": {"EUR", "USD"},
                        },
                        "start_date": {"type": "string", "format": "date"},
                        "active": {"type": "boolean"},
                        "skills": {"type": "array", "item_type": "string"},
                        "address": {
                            "type": "object",
                            "fields": {
                                "street": {"type": "string"},
                                "city": {"type": "string"},
                                "zip": {"type": "string"},
                                "country": {"type": "string"},
                            },
                        },
                        "projects": {
                            "type": "array",
                            "item_type": "object",
                            "item_fields": {
                                "name": {"type": "string"},
                                "role": {"type": "string"},
                                "hours_per_week": {"type": "integer"},
                            },
                        },
                        "manager_id": {"type": "integer", "nullable": True},
                        "phone": {"type": "string", "nullable": True},
                    },
                },
            },
        }
