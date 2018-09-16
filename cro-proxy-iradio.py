from flask import Flask, request, Response
from feedgen.feed import FeedGenerator
import requests
import lxml.html
from lxml.cssselect import CSSSelector
import re
import datetime
import pytz


app = Flask(__name__)

URL_IRADIO = 'https://hledani.rozhlas.cz/iRadio/?porad[]=%s'
URL_APP = 'https://app.evandar.cz/crofeed/'
APPNAME = 'Cesky Rozhlas iRadio Podcast Enabler'


def get_html(url):
    resp = requests.get(url, verify=False)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    return resp.text

def get_tree_from_link(link):
    html = get_html(link)
    tree = lxml.html.fromstring(html)
    return tree

def canonical_time(format, string):
    tz = pytz.timezone('Europe/Prague')
    return tz.localize(datetime.datetime.strptime(string, format))

def process_link_player(link, aid):
    MP3_LINK = "https://media.rozhlas.cz/_audio/{audioid}.mp3"
    DATETIME_FORMAT = '(%d.%m.%Y %H:%M)'

    tree = get_tree_from_link(link)
    node_date = tree.cssselect("div#block-track-player div.content h3 em")
    node_desc = tree.cssselect("div#block-track-player div.content p")[:1]

    assert(len(node_date) == 1)
    assert(len(node_desc) == 1)

    ret = {'title': node_desc[0].text_content(),
           'link': MP3_LINK.format(audioid=aid),
           'published': canonical_time(DATETIME_FORMAT, node_date[0].text_content()),
           'length': 0}
    print(link, ret)
    return [ret]

def process_link_article(link):
    DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S'

    tree = get_tree_from_link(link)
    date_node = tree.cssselect("meta[property='article:published_time']")
    link_nodes = tree.cssselect("div.sm2-playlist-wrapper a")
    ret = list()

    for link_node in link_nodes:
        entry = {'title': link_node.text_content(),
                 'link': link_node.get('href', None),
                 'published': canonical_time(DATETIME_FORMAT, date_node[0].get('content', '1970-01-01T00:00:00')),
                 'length': 0}
        print(link, entry)
        ret.append(entry)
    return ret

def process(link):
    IPLAYER = "http(s)?://prehravac.rozhlas.cz/audio/(?P<id>\d+)"

    m = re.match(IPLAYER, link)
    if m is not None:
        return process_link_player(link, m.group('id'))
    else:
        return process_link_article(link)

def parse(html):
    tree = lxml.html.fromstring(html)
    items = tree.cssselect('ul.box-audio-archive li.item')

    ret = []

    for item in items:
        link_node = item.cssselect('.action-player a')
        assert(len(link_node) == 1)
        link = link_node[0].get('href', None)

        entries = process(link)
        for e in entries:
            ret.append(e)
    return ret

def create_feed(porad, request_url):
    entries = parse(get_html(URL_IRADIO % porad))

    fg = FeedGenerator()
    fg.load_extension('podcast')

    fg.id('{}/porad?id={}'.format(URL_APP, porad))
    fg.title('{}: {}'.format(porad, APPNAME))
    fg.subtitle('{}: {}'.format(porad, APPNAME))
    fg.description('{}. Vytváří RSS podcast feed pro pořady, ke kterým je Český rozhlas na svém webu neposkytuje.'.format(APPNAME))

    fg.link(href=request_url, rel='self')
    # fg.link(href=URL_APP, rel='alternate')
    # fg.link(href=URL_IRADIO % porad, rel='via')

    fg.language('cs')
    fg.rights('Tato aplikace pouze na odkazuje na data Českého Rozhlasu.')
    fg.pubDate(max(entries, key=lambda x: x['published'])['published'])
    #  fg.icon(url)
    #  fg.image(url='',
    #          title='',
    #          link='',
    #          width='',
    #          height='',
    #          description='')

    for entry in entries:
        fe = fg.add_entry()
        fe.id(entry['link'])
        fe.enclosure(entry['link'], length=entry['length'], type='audio/mpeg')
        fe.published(entry['published'])
        fe.title(entry['title'])
        fe.description(entry['title'])

    return fg


@app.route("/")
@app.route('/feed.xml')
def podcast():
    show_id = request.args.get('id', None)
    if show_id is None:
        return Response('Specify show ... ?id=show name', mimetype='text/html')

    fg = create_feed(show_id, request.path)
    rss = fg.rss_str(pretty=True)
    return Response(rss, mimetype='application/rss+xml')


if __name__ == '__main__':
    app.run()
