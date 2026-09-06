from dataclasses import dataclass

@dataclass(frozen=True)
class Money:
    cents: int

    def __post_init__(self):
        if not isinstance(self.cents, int) or isinstance(self.cents, bool):
            raise TypeError("Money cents must be an integer")

    def __add__(self, other: "Money") -> "Money":
        return Money(self.cents + other.cents)

    def __sub__(self, other: "Money") -> "Money":
        return Money(self.cents - other.cents)

    def __mul__(self, multiplier: int) -> "Money":
        return Money(self.cents * multiplier)

    def __repr__(self) -> str:
        return f"Money({self.cents})"


@dataclass(frozen=True)
class Minutes:
    value: int

    def __post_init__(self):
        if not isinstance(self.value, int) or isinstance(self.value, bool):
            raise TypeError("Minutes value must be an integer")
        if self.value < 0:
            raise ValueError("Minutes cannot be negative")

    def __repr__(self) -> str:
        return f"Minutes({self.value})"
