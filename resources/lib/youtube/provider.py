from resources.lib.youtube.helper import v2

__author__ = 'bromix'

from resources.lib import kodion
from resources.lib.kodion.utils import FunctionCache
from resources.lib.kodion.items import *
from .youtube_client import YouTubeClient
from .helper import v3, v2, ResourceManager
from .youtube_exceptions import YouTubeException, LoginException


class Provider(kodion.AbstractProvider):
    LOCAL_MAP = {'youtube.channels': 30500,
                 'youtube.playlists': 30501,
                 'youtube.go_to_channel': 30502,
                 'youtube.subscriptions': 30504,
                 'youtube.unsubscribe': 30505,
                 'youtube.subscribe': 30506,
                 'youtube.my_channel': 30507,
                 'youtube.watch_later': 30107,
                 'youtube.liked.videos': 30508,
                 'youtube.history': 30509,
                 'youtube.my_subscriptions': 30510}

    def __init__(self):
        kodion.AbstractProvider.__init__(self)

        self._client = None
        self._resource_manager = None
        self._is_logged_in = False
        pass

    def get_client(self, context):
        # set the items per page (later)
        items_per_page = context.get_settings().get_items_per_page()
        # TODO: get language or region to configure the client correctly

        access_manager = context.get_access_manager()
        access_token = access_manager.get_access_token()
        if access_manager.is_new_login_credential() or not access_token or access_manager.is_access_token_expired():
            # reset access_token
            access_manager.update_access_token('')
            # we clear the cache, so none cached data of an old account will be displayed.
            context.get_function_cache().clear()
            # reset the client
            self._client = None
            pass

        if not self._client:
            if access_manager.has_login_credentials():
                username, password = access_manager.get_login_credentials()
                access_token = access_manager.get_access_token()

                # create a new access_token
                if not access_token:
                    access_token, expires = YouTubeClient().authenticate(username, password)
                    access_manager.update_access_token(access_token, expires)
                    pass

                self._is_logged_in = access_token != ''
                self._client = YouTubeClient(items_per_page=items_per_page, access_token=access_token)
            else:
                self._client = YouTubeClient(items_per_page=items_per_page)
                pass
            pass

        return self._client

    def get_resource_manager(self, context):
        if not self._resource_manager:
            self._resource_manager = ResourceManager(context, self.get_client(context))
            pass
        return self._resource_manager

    def get_alternative_fanart(self, context):
        return self.get_fanart(context)

    def get_fanart(self, context):
        return context.create_resource_path('media', 'fanart.jpg')

    @kodion.RegisterProviderPath('^/channel/(?P<channel_id>.*)/playlist/(?P<playlist_id>.*)/$')
    def _on_playlist(self, context, re_match):
        self._set_content_type(context, kodion.constants.content_type.EPISODES)

        result = []

        playlist_id = re_match.group('playlist_id')
        page_token = context.get_param('page_token', '')

        json_data = context.get_function_cache().get(FunctionCache.ONE_DAY, self.get_client(context).get_playlist_items,
                                                     playlist_id, page_token)
        result.extend(v3.response_to_items(self, context, json_data))

        return result

    @kodion.RegisterProviderPath('^/channel/(?P<channel_id>.*)/playlists/$')
    def _on_channel_playlists(self, context, re_match):
        self._set_content_type(context, kodion.constants.content_type.EPISODES)

        result = []

        channel_id = re_match.group('channel_id')
        page_token = context.get_param('page_token', '')

        json_data = context.get_function_cache().get(FunctionCache.ONE_HOUR, self.get_client(context).get_playlists,
                                                     channel_id, page_token)
        result.extend(v3.response_to_items(self, context, json_data))

        return result

    @kodion.RegisterProviderPath('^/channel/(?P<channel_id>.*)/$')
    def _on_channel(self, context, re_match):
        self._set_content_type(context, kodion.constants.content_type.EPISODES)

        resource_manager = ResourceManager(context, self.get_client(context))

        result = []

        channel_id = re_match.group('channel_id')
        channel_fanarts = resource_manager.get_fanarts([channel_id])
        page = int(context.get_param('page', 1))
        page_token = context.get_param('page_token', '')

        if page == 1:
            playlists_item = DirectoryItem('[B]' + context.localize(self.LOCAL_MAP['youtube.playlists']) + '[/B]',
                                           context.create_uri(['channel', channel_id, 'playlists']),
                                           image=context.create_resource_path('media', 'playlist.png'))
            playlists_item.set_fanart(channel_fanarts.get(channel_id, self.get_fanart(context)))
            result.append(playlists_item)
            pass

        playlists = resource_manager.get_related_playlists(channel_id)
        upload_playlist = playlists.get('uploads', '')
        if upload_playlist:
            json_data = context.get_function_cache().get(FunctionCache.ONE_MINUTE * 5,
                                                         self.get_client(context).get_playlist_items, upload_playlist,
                                                         page_token)
            result.extend(v3.response_to_items(self, context, json_data))
            pass

        return result

    @kodion.RegisterProviderPath('^/play/(?P<video_id>.*)/$')
    def _on_play(self, context, re_match):
        vq = context.get_settings().get_video_quality()

        def _compare(item):
            return vq - item['format']['height']

        video_id = re_match.group('video_id')

        try:
            video_streams = self.get_client(context).get_video_streams(context, video_id)
            video_stream = kodion.utils.find_best_fit(video_streams, _compare)
            video_item = VideoItem(video_id,
                                   video_stream['url'])
            return video_item
        except YouTubeException, ex:
            message = ex.get_message()
            message = kodion.utils.strip_html_from_text(message)
            context.get_ui().show_notification(message, time_milliseconds=30000)
            pass

        return False

    @kodion.RegisterProviderPath('^/subscription/(?P<method>.*)/(?P<subscription_id>.*)/$')
    def _on_subscription(self, context, re_match):
        method = re_match.group('method')
        subscription_id = re_match.group('subscription_id')

        if method == 'remove':
            self.get_client(context).unsubscribe(subscription_id)
            context.get_ui().refresh_container()
            pass
        elif method == 'add':
            self.get_client(context).subscribe(subscription_id)
            pass
        return True

    @kodion.RegisterProviderPath('^/my_subscriptions/$')
    def _on_mysubscriptions(self, context, re_match):
        self._set_content_type(context, kodion.constants.content_type.EPISODES)

        result = []

        json_data = self.get_client(context).get_uploaded_videos_of_subscriptions()
        result.extend(v2.response_to_items(self, context, json_data))

        return result

    @kodion.RegisterProviderPath('^/subscriptions/$')
    def _on_subscriptions(self, context, re_match):
        result = []

        page_token = context.get_param('page_token', '')
        # no caching
        json_data = self.get_client(context).get_subscription('mine', page_token=page_token)
        result.extend(v3.response_to_items(self, context, json_data))

        return result

    def on_search(self, search_text, context, re_match):
        self._set_content_type(context, kodion.constants.content_type.EPISODES)

        result = []

        page_token = context.get_param('page_token', '')
        search_type = context.get_param('search_type', 'video')
        page = int(context.get_param('page', 1))

        if page == 1 and search_type == 'video':
            channel_params = {}
            channel_params.update(context.get_params())
            channel_params['search_type'] = 'channel'
            channel_item = DirectoryItem('[B]' + context.localize(self.LOCAL_MAP['youtube.channels']) + '[/B]',
                                         context.create_uri([context.get_path()], channel_params),
                                         image=context.create_resource_path('media', 'channel.png'))
            channel_item.set_fanart(self.get_fanart(context))
            result.append(channel_item)

            playlist_params = {}
            playlist_params.update(context.get_params())
            playlist_params['search_type'] = 'playlist'
            playlist_item = DirectoryItem('[B]' + context.localize(self.LOCAL_MAP['youtube.playlists']) + '[/B]',
                                          context.create_uri([context.get_path()], playlist_params),
                                          image=context.create_resource_path('media', 'playlist.png'))
            playlist_item.set_fanart(self.get_fanart(context))
            result.append(playlist_item)
            pass

        json_data = context.get_function_cache().get(FunctionCache.ONE_MINUTE * 10, self.get_client(context).search,
                                                     q=search_text, search_type=search_type, page_token=page_token)
        result.extend(v3.response_to_items(self, context, json_data))

        return result

    def on_root(self, context, re_match):
        self.get_client(context)
        resource_manager = self.get_resource_manager(context)

        result = []

        if self._is_logged_in:
            # my subscription
            my_subscriptions_item = DirectoryItem(context.localize(self.LOCAL_MAP['youtube.my_subscriptions']),
                                                  context.create_uri(['my_subscriptions']),
                                                  context.create_resource_path('media', 'new_uploads.png'))
            my_subscriptions_item.set_fanart(self.get_fanart(context))
            result.append(my_subscriptions_item)
            pass

        # search
        search_item = kodion.items.create_search_item(context)
        search_item.set_image(context.create_resource_path('media', 'search.png'))
        search_item.set_fanart(self.get_fanart(context))
        result.append(search_item)

        # subscriptions
        if self._is_logged_in:
            playlists = resource_manager.get_related_playlists(channel_id='mine')

            # my channel
            my_channel_item = DirectoryItem(context.localize(self.LOCAL_MAP['youtube.my_channel']),
                                            context.create_uri(['channel', 'mine']),
                                            image=context.create_resource_path('media', 'channel.png'))
            my_channel_item.set_fanart(self.get_fanart(context))
            result.append(my_channel_item)

            # watch later
            if 'watchLater' in playlists:
                watch_later_item = DirectoryItem(context.localize(self.LOCAL_MAP['youtube.watch_later']),
                                                 context.create_uri(
                                                     ['channel', 'mine', 'playlist', playlists['watchLater']]),
                                                 context.create_resource_path('media', 'watch_later.png'))
                watch_later_item.set_fanart(self.get_fanart(context))
                result.append(watch_later_item)
                pass

            # liked videos
            if 'likes' in playlists:
                liked_videos_item = DirectoryItem(context.localize(self.LOCAL_MAP['youtube.liked.videos']),
                                                  context.create_uri(
                                                      ['channel', 'mine', 'playlist', playlists['likes']]),
                                                  context.create_resource_path('media', 'likes.png'))
                liked_videos_item.set_fanart(self.get_fanart(context))
                result.append(liked_videos_item)
                pass

            # history
            if 'watchHistory' in playlists:
                watch_history_item = DirectoryItem(context.localize(self.LOCAL_MAP['youtube.history']),
                                                   context.create_uri(
                                                       ['channel', 'mine', 'playlist', playlists['watchHistory']]),
                                                   context.create_resource_path('media', 'history.png'))
                watch_history_item.set_fanart(self.get_fanart(context))
                result.append(watch_history_item)
                pass

            # (my) playlists
            playlists_item = DirectoryItem(context.localize(self.LOCAL_MAP['youtube.playlists']),
                                           context.create_uri(['channel', 'mine', 'playlists']),
                                           context.create_resource_path('media', 'playlist.png'))
            playlists_item.set_fanart(self.get_fanart(context))
            result.append(playlists_item)

            # subscriptions
            subscriptions_item = DirectoryItem(context.localize(self.LOCAL_MAP['youtube.subscriptions']),
                                               context.create_uri(['subscriptions']),
                                               image=context.create_resource_path('media', 'channel.png'))
            subscriptions_item.set_fanart(self.get_fanart(context))
            result.append(subscriptions_item)
            pass

        return result

    def _set_content_type(self, context, content_type):
        if content_type == kodion.constants.content_type.EPISODES:
            context.set_content_type(content_type)
            pass
        pass

    def handle_exception(self, context, exception_to_handle):
        if isinstance(exception_to_handle, LoginException):
            context.get_access_manager().update_access_token('')
            context.get_ui().show_notification('Login Failed')
            context.get_ui().open_settings()
            return False

        return True

    pass