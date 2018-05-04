import httplib2
from apiclient.discovery import build
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow

flow = flow_from_clientsecrets(
    'client_secret.json', scope="https://www.googleapis.com/auth/youtube", message="FAILED")
storage = Storage("youtube-oauth2.json")
credentials = storage.get()  # Warned about non-existent file.
args = argparser.parse_args()
if credentials is None or credentials.invalid:
    credentials = run_flow(flow, storage, args)
youtube = build("youtube", "v3", http=credentials.authorize(httplib2.Http()))
VALID_BROADCAST_STATUSES = ("all", "active", "completed", "upcoming",)
list_broadcasts_request = youtube.liveBroadcasts().list(
    part="id,snippet", broadcastStatus="upcoming")
while list_broadcasts_request:
    list_broadcasts_response = list_broadcasts_request.execute()
    for broadcast in list_broadcasts_response.get("items", []):
        print "%s (%s)" % (broadcast["snippet"]["title"], broadcast["id"])
    list_broadcasts_request = youtube.liveBroadcasts().list_next(
        list_broadcasts_request, list_broadcasts_response)
