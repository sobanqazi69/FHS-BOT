import logging
import gspread

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class EmailReader:
    def __init__(self, credentials_file: str, spreadsheet_id: str):
        self.spreadsheet_id = spreadsheet_id
        self.client = gspread.service_account(filename=credentials_file, scopes=SCOPES)
        self._emails: list[str] = []
        self._rows: list[int] = []
        self._column: int = 1
        self._sheet = None
        self._index = 0

    def load(self, sheet_name: str = "Sheet1", column: int = 1):
        self._column = column
        self._sheet = self.client.open_by_key(self.spreadsheet_id).worksheet(sheet_name)
        all_values = self._sheet.col_values(column)
        self._emails = []
        self._rows = []
        for i, v in enumerate(all_values, start=1):
            if v.strip():
                self._emails.append(v.strip())
                self._rows.append(i)
        self._index = 0
        logger.info(f"Loaded {len(self._emails)} email(s) from sheet.")

    def mark_last_green(self):
        idx = self._index - 1
        if self._sheet is None or idx < 0 or idx >= len(self._rows):
            logger.warning("Cannot mark green — no email to mark.")
            return
        try:
            col_letter = chr(ord("A") + self._column - 1)
            cell = f"{col_letter}{self._rows[idx]}"
            self._sheet.format(cell, {
                "backgroundColor": {"red": 0.20, "green": 0.80, "blue": 0.20}
            })
            logger.info(f"Marked {self._emails[idx]} green in sheet (cell {cell}).")
        except Exception as e:
            logger.error(f"Failed to mark cell green: {e}")

    def get_next(self) -> str | None:
        if self._index >= len(self._emails):
            logger.info("No more emails.")
            return None
        email = self._emails[self._index]
        self._index += 1
        logger.info(f"Got email [{self._index}/{len(self._emails)}]: {email}")
        return email

    def get_first(self) -> str | None:
        if not self._emails:
            logger.warning("Email list is empty. Did you call load()?")
            return None
        return self._emails[0]

    @property
    def all_emails(self) -> list[str]:
        return list(self._emails)
