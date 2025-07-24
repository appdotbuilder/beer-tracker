from decimal import Decimal
from datetime import date, datetime
from typing import List, Optional

from nicegui import ui
from sqlmodel import select

from app.database import get_session
from app.models import BeerEntry, BeerEntryCreate, CurrencyEnum, ExchangeRateService


class TextStyles:
    HEADING = "text-2xl font-bold text-gray-800 mb-6"
    SUBHEADING = "text-lg font-semibold text-gray-700 mb-4"
    BODY = "text-base text-gray-600 leading-relaxed"
    CAPTION = "text-sm text-gray-500"
    ERROR = "text-sm text-red-600 mt-1"


class BeerTrackerService:
    """Service layer for beer tracking operations."""

    @staticmethod
    async def create_beer_entry(entry_data: BeerEntryCreate) -> Optional[BeerEntry]:
        """Create a new beer entry with automatic currency conversion."""
        try:
            # Calculate both EUR and USD prices using the exchange rate service
            eur_price, usd_price, exchange_rate = await ExchangeRateService.calculate_prices(
                entry_data.original_price, entry_data.original_currency, entry_data.purchase_date
            )

            # Create the database entry
            beer_entry = BeerEntry(
                beer_name=entry_data.beer_name,
                original_price=entry_data.original_price,
                original_currency=entry_data.original_currency,
                purchase_date=entry_data.purchase_date,
                eur_price=eur_price,
                usd_price=usd_price,
                exchange_rate=exchange_rate,
            )

            with get_session() as session:
                session.add(beer_entry)
                session.commit()
                session.refresh(beer_entry)
                return beer_entry

        except Exception as e:
            ui.notify(f"Error creating beer entry: {str(e)}", type="negative")
            return None

    @staticmethod
    def get_all_beer_entries() -> List[BeerEntry]:
        """Get all beer entries from the database."""
        with get_session() as session:
            statement = select(BeerEntry)
            return list(session.exec(statement))

    @staticmethod
    def delete_beer_entry(entry_id: int) -> bool:
        """Delete a beer entry by ID."""
        try:
            with get_session() as session:
                entry = session.get(BeerEntry, entry_id)
                if entry is not None:
                    session.delete(entry)
                    session.commit()
                    return True
            return False
        except Exception as e:
            ui.notify(f"Error deleting entry: {str(e)}", type="negative")
            return False


def create_beer_entry_form():
    """Create the form for adding new beer entries."""

    with ui.card().classes("w-full max-w-md p-6 shadow-lg rounded-lg mb-6"):
        ui.label("Add New Beer Entry").classes(TextStyles.SUBHEADING)

        # Form inputs
        ui.label("Beer Name").classes("text-sm font-medium text-gray-700 mb-1")
        beer_name_input = ui.input(placeholder="Enter beer name").classes("w-full mb-4")

        ui.label("Original Price").classes("text-sm font-medium text-gray-700 mb-1")
        original_price_input = ui.number(format="%.2f", placeholder="0.00").classes("w-full mb-4")

        ui.label("Original Currency").classes("text-sm font-medium text-gray-700 mb-1")
        currency_select = ui.select(options=["EUR", "USD"], value="EUR").classes("w-full mb-4")

        ui.label("Purchase Date").classes("text-sm font-medium text-gray-700 mb-1")
        purchase_date_input = ui.date(value=date.today().isoformat()).classes("w-full mb-4")

        # Error message container
        error_message = ui.label("").classes(TextStyles.ERROR).style("display: none")

        # Loading indicator
        loading_indicator = ui.row().classes("items-center gap-2").style("display: none")
        with loading_indicator:
            ui.spinner(size="sm")
            ui.label("Processing...").classes(TextStyles.CAPTION)

        async def add_beer_entry():
            """Handle form submission."""
            # Validate inputs
            if not beer_name_input.value or not beer_name_input.value.strip():
                show_error("Beer name is required")
                return

            if original_price_input.value is None or original_price_input.value <= 0:
                show_error("Please enter a valid price greater than 0")
                return

            if not currency_select.value:
                show_error("Please select a currency")
                return

            if not purchase_date_input.value:
                show_error("Please select a purchase date")
                return

            # Clear any previous errors
            hide_error()

            # Show loading indicator
            loading_indicator.style("display: flex")
            add_button.set_enabled(False)

            try:
                # Parse the date - it comes as a string from the UI
                purchase_date_str = purchase_date_input.value
                if isinstance(purchase_date_str, str):
                    purchase_date_obj = datetime.fromisoformat(purchase_date_str).date()
                else:
                    purchase_date_obj = purchase_date_str

                # Create the entry data
                entry_data = BeerEntryCreate(
                    beer_name=beer_name_input.value.strip(),
                    original_price=Decimal(str(original_price_input.value)),
                    original_currency=CurrencyEnum(currency_select.value),
                    purchase_date=purchase_date_obj,
                )

                # Create the beer entry
                result = await BeerTrackerService.create_beer_entry(entry_data)

                if result is not None:
                    ui.notify("Beer entry added successfully!", type="positive")
                    # Clear the form
                    beer_name_input.set_value("")
                    original_price_input.set_value(None)
                    currency_select.set_value("EUR")
                    purchase_date_input.set_value(date.today().isoformat())
                    # Refresh the beer list
                    refresh_beer_list()
                else:
                    show_error("Failed to add beer entry. Please try again.")

            except Exception as e:
                show_error(f"Error: {str(e)}")
            finally:
                # Hide loading indicator
                loading_indicator.style("display: none")
                add_button.set_enabled(True)

        def show_error(message: str):
            error_message.set_text(message)
            error_message.style("display: block")

        def hide_error():
            error_message.style("display: none")

        # Submit button
        with ui.row().classes("gap-2 justify-end mt-4"):
            add_button = ui.button("Add Beer Entry", on_click=add_beer_entry).classes(
                "bg-blue-500 text-white px-6 py-2 rounded hover:bg-blue-600"
            )


def create_beer_list():
    """Create the list display for all beer entries."""

    with ui.card().classes("w-full p-6 shadow-lg rounded-lg"):
        header_row = ui.row().classes("w-full items-center justify-between mb-4")
        with header_row:
            ui.label("Your Beer Collection").classes(TextStyles.SUBHEADING + " mb-0")
            ui.button("Refresh", on_click=lambda: refresh_beer_list()).props("outline").classes("text-blue-500")

        # Container for the beer entries
        global beer_list_container
        beer_list_container = ui.column().classes("w-full gap-4")

        # Initial load
        refresh_beer_list()


def refresh_beer_list():
    """Refresh the beer list display."""
    global beer_list_container

    if "beer_list_container" not in globals():
        return

    # Clear existing content
    beer_list_container.clear()

    # Get all beer entries
    entries = BeerTrackerService.get_all_beer_entries()

    if not entries:
        with beer_list_container:
            ui.label("No beer entries yet. Add your first beer above!").classes(
                TextStyles.BODY + " text-center py-8 text-gray-400"
            )
        return

    # Create table headers
    with beer_list_container:
        # Table header
        with ui.row().classes("w-full bg-gray-50 p-4 rounded-t-lg font-semibold text-gray-700"):
            ui.label("Beer Name").classes("flex-1 min-w-0")
            ui.label("Original").classes("w-24 text-center")
            ui.label("Purchase Date").classes("w-32 text-center")
            ui.label("EUR Price").classes("w-24 text-center")
            ui.label("USD Price").classes("w-24 text-center")
            ui.label("Actions").classes("w-20 text-center")

        # Table rows
        for entry in entries:
            create_beer_entry_row(entry)


def create_beer_entry_row(entry: BeerEntry):
    """Create a single row for a beer entry."""

    with ui.row().classes("w-full p-4 border-b border-gray-200 hover:bg-gray-50 items-center"):
        # Beer name
        ui.label(entry.beer_name).classes("flex-1 min-w-0 font-medium text-gray-800 truncate")

        # Original price and currency
        original_display = f"{entry.original_price:.2f} {entry.original_currency.value}"
        ui.label(original_display).classes("w-24 text-center text-sm text-gray-600")

        # Purchase date
        date_display = entry.purchase_date.strftime("%Y-%m-%d")
        ui.label(date_display).classes("w-32 text-center text-sm text-gray-600")

        # EUR price
        eur_display = f"€{entry.eur_price:.2f}"
        ui.label(eur_display).classes("w-24 text-center text-sm font-medium text-green-600")

        # USD price
        usd_display = f"${entry.usd_price:.2f}"
        ui.label(usd_display).classes("w-24 text-center text-sm font-medium text-blue-600")

        # Delete button
        if entry.id is not None:
            ui.button(
                icon="delete",
                on_click=lambda e, entry_id=entry.id: delete_beer_entry(entry_id) if entry_id is not None else None,
            ).props("flat color=negative size=sm").classes("w-20")


async def delete_beer_entry(entry_id: int):
    """Delete a beer entry with confirmation."""

    with ui.dialog() as dialog, ui.card():
        ui.label("Are you sure you want to delete this beer entry?").classes("mb-4")
        with ui.row().classes("gap-2 justify-end"):
            ui.button("Cancel", on_click=lambda: dialog.submit("cancel")).props("outline")
            ui.button("Delete", on_click=lambda: dialog.submit("delete")).props("color=negative")

    result = await dialog

    if result == "delete":
        success = BeerTrackerService.delete_beer_entry(entry_id)
        if success:
            ui.notify("Beer entry deleted successfully", type="positive")
            refresh_beer_list()
        else:
            ui.notify("Failed to delete beer entry", type="negative")


def create():
    """Create the beer tracker application."""

    @ui.page("/")
    def beer_tracker_page():
        # Apply modern theme colors
        ui.colors(
            primary="#2563eb",  # Professional blue
            secondary="#64748b",  # Subtle gray
            accent="#10b981",  # Success green
            positive="#10b981",
            negative="#ef4444",  # Error red
            warning="#f59e0b",  # Warning amber
            info="#3b82f6",  # Info blue
        )

        # Page header
        with ui.row().classes("w-full justify-center mb-8"):
            with ui.column().classes("items-center text-center"):
                ui.label("🍺 Personal Beer Tracker").classes("text-3xl font-bold text-gray-800 mb-2")
                ui.label("Track your beer purchases with automatic currency conversion").classes(TextStyles.BODY)

        # Main content
        with ui.row().classes("w-full max-w-6xl mx-auto gap-6").style("align-items: flex-start"):
            # Left column - Add beer form
            with ui.column().classes("w-full md:w-1/3"):
                create_beer_entry_form()

            # Right column - Beer list
            with ui.column().classes("w-full md:w-2/3"):
                create_beer_list()
