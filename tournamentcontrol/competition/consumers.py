from channels.generic.websockets import WebsocketDemultiplexer

from .models import MatchBinding, PersonBinding


class Demultiplexer(WebsocketDemultiplexer):

    http_user = True

    consumers = {
        'match': MatchBinding.consumer,
        'person': PersonBinding.consumer,
    }

    def connection_groups(self):
        return [c + '-updates' for c in self.consumers]
