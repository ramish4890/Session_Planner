"""Google Sheets export via OAuth."""
import os
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']


def get_credentials():
    """Get or refresh OAuth credentials."""
    creds = None
    token_path = 'token.json'

    if os.path.exists(token_path):
        with open(token_path, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('client_secret.json'):
                raise FileNotFoundError("client_secret.json not found. See README for setup.")

            flow = InstalledAppFlow.from_client_secrets_file('client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)

    return creds


def export_to_gsheets(workbook, title="Session Schedule"):
    """
    Export openpyxl workbook to Google Sheets.
    Returns the spreadsheet URL.
    """
    creds = get_credentials()
    service = build('sheets', 'v4', credentials=creds)

    # Create new spreadsheet
    spreadsheet = {
        'properties': {'title': title},
        'sheets': []
    }

    result = service.spreadsheets().create(body=spreadsheet).execute()
    spreadsheet_id = result['spreadsheetId']

    # Write each sheet
    requests = []
    for idx, ws in enumerate(workbook.worksheets):
        sheet_title = ws.title

        # Add sheet (first one already exists)
        if idx > 0:
            requests.append({
                'addSheet': {
                    'properties': {'title': sheet_title}
                }
            })

    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()

    # Write data to each sheet
    for ws in workbook.worksheets:
        sheet_title = ws.title
        values = []

        for row in ws.iter_rows(values_only=True):
            values.append(list(row))

        body = {'values': values}

        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_title}'!A1",
            valueInputOption='RAW',
            body=body
        ).execute()

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    return url
