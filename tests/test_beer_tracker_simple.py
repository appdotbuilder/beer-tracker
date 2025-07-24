import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import patch

from nicegui.testing import User

from app.database import reset_db, get_session
from app.models import BeerEntry, BeerEntryCreate, CurrencyEnum, ExchangeRateService
from app.beer_tracker import BeerTrackerService


@pytest.fixture()
def new_db():
    reset_db()
    yield
    reset_db()


class TestBeerTrackerCore:
    """Test core beer tracker functionality."""

    def test_currency_enum_values(self):
        """Test CurrencyEnum has correct values."""
        assert CurrencyEnum.EUR.value == "EUR"
        assert CurrencyEnum.USD.value == "USD"
        assert len(list(CurrencyEnum)) == 2

    def test_beer_entry_creation(self):
        """Test creating a BeerEntry instance."""
        entry = BeerEntry(
            beer_name="Test Beer",
            original_price=Decimal("10.50"),
            original_currency=CurrencyEnum.EUR,
            purchase_date=date(2023, 1, 1),
            eur_price=Decimal("10.50"),
            usd_price=Decimal("11.55"),
            exchange_rate=Decimal("1.1"),
        )

        assert entry.beer_name == "Test Beer"
        assert entry.original_price == Decimal("10.50")
        assert entry.original_currency == CurrencyEnum.EUR
        assert entry.eur_price == Decimal("10.50")
        assert entry.usd_price == Decimal("11.55")
        assert entry.exchange_rate == Decimal("1.1")

    def test_beer_entry_create_schema(self):
        """Test BeerEntryCreate schema validation."""
        entry_data = BeerEntryCreate(
            beer_name="Test Beer",
            original_price=Decimal("15.75"),
            original_currency=CurrencyEnum.USD,
            purchase_date=date(2023, 6, 15),
        )

        assert entry_data.beer_name == "Test Beer"
        assert entry_data.original_price == Decimal("15.75")
        assert entry_data.original_currency == CurrencyEnum.USD
        assert entry_data.purchase_date == date(2023, 6, 15)


class TestBeerTrackerService:
    """Test the beer tracker service layer."""

    def test_get_all_beer_entries_empty(self, new_db):
        """Test getting beer entries when database is empty."""
        entries = BeerTrackerService.get_all_beer_entries()
        assert entries == []

    def test_get_all_beer_entries_with_data(self, new_db):
        """Test getting beer entries with data in database."""
        # Create test entries directly in database
        with get_session() as session:
            entry1 = BeerEntry(
                beer_name="Beer One",
                original_price=Decimal("5.00"),
                original_currency=CurrencyEnum.EUR,
                purchase_date=date(2023, 1, 1),
                eur_price=Decimal("5.00"),
                usd_price=Decimal("5.50"),
                exchange_rate=Decimal("1.1"),
            )
            entry2 = BeerEntry(
                beer_name="Beer Two",
                original_price=Decimal("8.00"),
                original_currency=CurrencyEnum.USD,
                purchase_date=date(2023, 1, 2),
                eur_price=Decimal("7.20"),
                usd_price=Decimal("8.00"),
                exchange_rate=Decimal("0.9"),
            )
            session.add(entry1)
            session.add(entry2)
            session.commit()

        entries = BeerTrackerService.get_all_beer_entries()
        assert len(entries) == 2
        beer_names = [entry.beer_name for entry in entries]
        assert "Beer One" in beer_names
        assert "Beer Two" in beer_names

    def test_delete_beer_entry_success(self, new_db):
        """Test successful beer entry deletion."""
        # Create test entry
        with get_session() as session:
            entry = BeerEntry(
                beer_name="Test Beer",
                original_price=Decimal("5.00"),
                original_currency=CurrencyEnum.EUR,
                purchase_date=date(2023, 1, 1),
                eur_price=Decimal("5.00"),
                usd_price=Decimal("5.50"),
                exchange_rate=Decimal("1.1"),
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id

        # Delete the entry
        if entry_id is not None:
            result = BeerTrackerService.delete_beer_entry(entry_id)
            assert result is True

            # Verify it's deleted
            entries = BeerTrackerService.get_all_beer_entries()
            assert len(entries) == 0

    def test_delete_beer_entry_not_found(self, new_db):
        """Test deleting non-existent beer entry."""
        result = BeerTrackerService.delete_beer_entry(999)
        assert result is False

    @pytest.mark.asyncio
    async def test_create_beer_entry_success_mocked(self, new_db):
        """Test successful beer entry creation with mocked exchange rate."""
        with patch.object(ExchangeRateService, "calculate_prices") as mock_calc:
            mock_calc.return_value = (Decimal("8.50"), Decimal("10.00"), Decimal("1.176"))

            entry_data = BeerEntryCreate(
                beer_name="Test Beer",
                original_price=Decimal("10.00"),
                original_currency=CurrencyEnum.USD,
                purchase_date=date(2023, 1, 1),
            )

            result = await BeerTrackerService.create_beer_entry(entry_data)

            assert result is not None
            assert result.beer_name == "Test Beer"
            assert result.original_price == Decimal("10.00")
            assert result.original_currency == CurrencyEnum.USD
            assert result.eur_price == Decimal("8.50")
            assert result.usd_price == Decimal("10.00")
            assert result.exchange_rate == Decimal("1.176")


class TestExchangeRateService:
    """Test exchange rate service basic functionality."""

    @pytest.mark.asyncio
    async def test_same_currency_returns_one(self):
        """Test that same currency conversion returns 1.0."""
        rate = await ExchangeRateService.get_exchange_rate(CurrencyEnum.EUR, CurrencyEnum.EUR, date.today())
        assert rate == Decimal("1.0")

    @pytest.mark.asyncio
    async def test_same_currency_usd(self):
        """Test that same currency conversion returns 1.0 for USD."""
        rate = await ExchangeRateService.get_exchange_rate(CurrencyEnum.USD, CurrencyEnum.USD, date.today())
        assert rate == Decimal("1.0")


# UI Tests - Simple smoke tests
class TestBeerTrackerUI:
    """Basic UI integration tests."""

    @pytest.mark.asyncio
    async def test_page_loads_successfully(self, user: User, new_db):
        """Test that the main page loads without errors."""
        await user.open("/")

        # Check main elements are present
        await user.should_see("Personal Beer Tracker")
        await user.should_see("Add New Beer Entry")
        await user.should_see("Your Beer Collection")
        await user.should_see("No beer entries yet")

    @pytest.mark.asyncio
    async def test_beer_list_display_with_entries(self, user: User, new_db):
        """Test that beer entries are displayed correctly in the list."""
        # Create test entry in database
        with get_session() as session:
            entry = BeerEntry(
                beer_name="Sample Beer",
                original_price=Decimal("12.50"),
                original_currency=CurrencyEnum.EUR,
                purchase_date=date(2023, 6, 15),
                eur_price=Decimal("12.50"),
                usd_price=Decimal("13.75"),
                exchange_rate=Decimal("1.1"),
            )
            session.add(entry)
            session.commit()

        await user.open("/")

        # Should see the beer entry details
        await user.should_see("Sample Beer")
        await user.should_see("12.50 EUR")
        await user.should_see("€12.50")
        await user.should_see("$13.75")
        await user.should_see("2023-06-15")


# Edge Cases
class TestEdgeCases:
    """Test edge cases and validation."""

    def test_zero_price_handling(self):
        """Test that zero prices can be created but handled appropriately."""
        entry_data = BeerEntryCreate(
            beer_name="Free Beer",
            original_price=Decimal("0"),
            original_currency=CurrencyEnum.EUR,
            purchase_date=date.today(),
        )
        # Model allows zero, validation happens in UI layer
        assert entry_data.original_price == Decimal("0")

    def test_future_date_handling(self):
        """Test that future dates are allowed."""
        future_date = date(2030, 1, 1)
        entry_data = BeerEntryCreate(
            beer_name="Future Beer",
            original_price=Decimal("100.00"),
            original_currency=CurrencyEnum.EUR,
            purchase_date=future_date,
        )

        assert entry_data.purchase_date == future_date

    def test_empty_beer_name_handling(self):
        """Test that empty beer names are handled."""
        # This should be caught at the UI level, not the model level
        entry_data = BeerEntryCreate(
            beer_name="",
            original_price=Decimal("10.00"),
            original_currency=CurrencyEnum.EUR,
            purchase_date=date.today(),
        )

        # Model allows empty string, validation happens in UI
        assert entry_data.beer_name == ""

    def test_very_large_price(self):
        """Test handling of very large prices."""
        entry_data = BeerEntryCreate(
            beer_name="Expensive Beer",
            original_price=Decimal("999999.99"),
            original_currency=CurrencyEnum.EUR,
            purchase_date=date.today(),
        )

        assert entry_data.original_price == Decimal("999999.99")
