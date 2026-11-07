class Organization:
    """S1: Represents a company."""
    def __init__(self, org_id: str, name: str, country_code: str):
        self._org_id = org_id
        self._name = name
        self._country_code = country_code

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        if not value:
            raise ValueError("Organization name cannot be empty")
        self._name = value

    @property
    def country_code(self):
        return self._country_code

class User:
    """S1: Represents a user within an organization."""
    def __init__(self, email: str, password_hash: str, role: str):
        self._email = email
        self._password_hash = password_hash
        self._role = role

    @property
    def email(self):
        return self._email

    @email.setter
    def email(self, value):
        if "@" not in value:
            raise ValueError("Invalid email format")
        self._email = value

    @property
    def role(self):
        return self._role

    @role.setter
    def role(self, value):
        if value not in ["admin", "manager", "contributor"]:
            raise ValueError("Invalid role")
        self._role = value

class ActivityRecord:
    """S1: Represents an emission-generating activity."""
    def __init__(self, category: str, amount: float, unit: str):
        self._category = category
        self._amount = amount
        self._unit = unit

    @property
    def amount(self):
        return self._amount

    @amount.setter
    def amount(self, value):
        if value < 0:
            raise ValueError("Amount cannot be negative")
        self._amount = value

    @property
    def unit(self):
        return self._unit
