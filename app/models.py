from sqlmodel import SQLModel, Field
from datetime import datetime, date
from typing import Optional
from decimal import Decimal
from enum import Enum
import httpx


class CurrencyEnum(str, Enum):
    EUR = "EUR"
    USD = "USD"


# Persistent model for beer entries stored in database
class BeerEntry(SQLModel, table=True):
    __tablename__ = "beer_entries"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    beer_name: str = Field(max_length=200)
    original_price: Decimal = Field(decimal_places=2, max_digits=10)
    original_currency: CurrencyEnum
    purchase_date: date
    eur_price: Decimal = Field(decimal_places=2, max_digits=10)
    usd_price: Decimal = Field(decimal_places=2, max_digits=10)
    exchange_rate: Decimal = Field(decimal_places=6, max_digits=15)  # Store the exchange rate used
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Non-persistent schema for creating new beer entries
class BeerEntryCreate(SQLModel, table=False):
    beer_name: str = Field(max_length=200)
    original_price: Decimal = Field(decimal_places=2, max_digits=10)
    original_currency: CurrencyEnum
    purchase_date: date


# Non-persistent schema for beer entry responses/display
class BeerEntryResponse(SQLModel, table=False):
    id: int
    beer_name: str
    original_price: Decimal
    original_currency: CurrencyEnum
    purchase_date: date
    eur_price: Decimal
    usd_price: Decimal
    exchange_rate: Decimal
    created_at: datetime

    def dict_with_iso_date(self) -> dict:
        """Return dictionary with ISO formatted dates for JSON serialization"""
        data = self.model_dump()
        data["purchase_date"] = self.purchase_date.isoformat()
        data["created_at"] = self.created_at.isoformat()
        return data


# Non-persistent schema for updating beer entries (optional fields)
class BeerEntryUpdate(SQLModel, table=False):
    beer_name: Optional[str] = Field(default=None, max_length=200)
    original_price: Optional[Decimal] = Field(default=None, decimal_places=2, max_digits=10)
    original_currency: Optional[CurrencyEnum] = Field(default=None)
    purchase_date: Optional[date] = Field(default=None)


class ExchangeRateService:
    """Service for fetching historical exchange rates between EUR and USD."""

    # Using exchangerate-api.com as it provides free historical data
    BASE_URL = "https://api.exchangerate-api.com/v4/historical"

    @staticmethod
    async def get_exchange_rate(
        from_currency: CurrencyEnum, to_currency: CurrencyEnum, rate_date: date
    ) -> Optional[Decimal]:
        """
        Get historical exchange rate for a specific date.

        Args:
            from_currency: Source currency (EUR or USD)
            to_currency: Target currency (EUR or USD)
            rate_date: Date for which to get the exchange rate

        Returns:
            Exchange rate as Decimal, or None if unable to fetch
        """
        if from_currency == to_currency:
            return Decimal("1.0")

        try:
            # Format: https://api.exchangerate-api.com/v4/historical/EUR/2023-01-01
            url = f"{ExchangeRateService.BASE_URL}/{from_currency.value}/{rate_date.isoformat()}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                data = response.json()
                rates = data.get("rates", {})
                rate = rates.get(to_currency.value)

                if rate is not None:
                    return Decimal(str(rate))

        except (httpx.RequestError, httpx.HTTPStatusError, KeyError, ValueError):
            # If the API fails, we could fallback to a default rate or cached value
            # For now, return None to indicate failure
            pass

        return None

    @staticmethod
    async def calculate_prices(
        original_price: Decimal, original_currency: CurrencyEnum, purchase_date: date
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Calculate both EUR and USD prices for a beer entry.

        Args:
            original_price: The original price paid
            original_currency: The currency of the original price
            purchase_date: Date of purchase for exchange rate lookup

        Returns:
            Tuple of (eur_price, usd_price, exchange_rate_used)
        """
        if original_currency == CurrencyEnum.EUR:
            # Original is EUR, need to convert to USD
            exchange_rate = await ExchangeRateService.get_exchange_rate(
                CurrencyEnum.EUR, CurrencyEnum.USD, purchase_date
            )
            if exchange_rate is not None:
                eur_price = original_price
                usd_price = original_price * exchange_rate
                return eur_price, usd_price, exchange_rate
            else:
                # Fallback if API fails - use a default rate or keep original only
                return original_price, Decimal("0"), Decimal("1.0")

        else:  # original_currency == CurrencyEnum.USD
            # Original is USD, need to convert to EUR
            exchange_rate = await ExchangeRateService.get_exchange_rate(
                CurrencyEnum.USD, CurrencyEnum.EUR, purchase_date
            )
            if exchange_rate is not None:
                usd_price = original_price
                eur_price = original_price * exchange_rate
                return eur_price, usd_price, exchange_rate
            else:
                # Fallback if API fails
                return Decimal("0"), original_price, Decimal("1.0")
