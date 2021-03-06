# -*- coding: utf-8 -*-

import logging
import re
import json

from lostfilm.network_request import NetworkRequest
from lostfilm.serie import Serie
from lostfilm.episode import Episode
from common.quality import Quality
from common.helpers import TorrentLink

# anonymized_urls = plugin.get_storage().setdefault('anonymized_urls', [], ttl=24 * 60 * 7)
# return LostFilmScraper(
#                        max_workers=BATCH_SERIES_COUNT,
#                        series_cache=series_cache(),
#                        anonymized_urls=anonymized_urls)

class DomParser(object):
  def __init__(self):
    self.log = logging.getLogger(__name__)
    self.network_request = NetworkRequest()
  # def __init__(self, login, password, cookie_jar=None, xrequests_session=None, series_cache=None, max_workers=10,
  #              anonymized_urls=None):
  #   super(LostFilmScraper, self).__init__(xrequests_session, cookie_jar)
  #   self.series_cache = series_cache if series_cache is not None else {}
  #   self.max_workers = max_workers
  #   self.response = None
  #   self.has_more = None
  #   self.anonymized_urls = anonymized_urls if anonymized_urls is not None else []
  #   self.session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36'
  #   self.session.add_proxy_need_check(self._check_content_is_blocked)
  #   self.session.add_proxy_validator(self._validate_proxy)

  # Library Series
  def lostfilm_library(self):
    self.network_request.authorize()

    dom = self.network_request.fetchDom(self.network_request.base_url + '/my/type_1')
    serials_list_box = dom.find('div', {'class': 'serials-list-box'})
    rows = serials_list_box.find('div', {'class': 'serial-box'})
    series_list_items = []

    for row in rows:
      link = row.find('a', {'href': '/series/.+?', 'class': 'body'})

      total_episodes_count, watched_episodes_count = self.series_episode_count(row)

      series_data = [
        self.series_id(row),
        self.series_code(link),
        link.find('div', {'class': 'title-en'}).text,
        link.find('div', {'class': 'title-ru'}).text,
        total_episodes_count,
        watched_episodes_count
      ]

      series_list_items.append(Serie(*series_data).list_item())

    return series_list_items

  def series_id(self, dom):
    subscribe_box = dom.find('div', {'class': 'subscribe-box'})
    if not subscribe_box:
      subscribe_box = dom.find('div', {'class': 'subscribe-box active'})

    id_attr = subscribe_box.attrs('id')[0]
    series_id = re.search('(\d+)', id_attr) if id_attr else ''
    return series_id.group(1) if series_id else 000

  def series_code(self, dom):
    href_attr = dom.attr('href')
    series_code = re.search('([^/]+$)', href_attr) if href_attr else ''
    return series_code.group(1) if series_code else ''

  def series_episode_count(self, row):
    episode_bar_pane = row.find('div', {'class': 'bar-pane'})

    total_episodes_bar = episode_bar_pane.find('div', {'class': 'bar'})
    total_episodes_count = total_episodes_bar.find('div', {'class': 'value'}).text
    if total_episodes_count == '':
      total_episodes_count = 0

    watched_episodes_bar = episode_bar_pane.find('div', {'class': 'bar-active'})
    watched_episodes_count = watched_episodes_bar.find('div', {'class': 'value'}).text
    if watched_episodes_count == '':
      watched_episodes_count = 0

    return total_episodes_count, watched_episodes_count

  # Episodes
  def series_episodes(self, series_id, series_code):
    self.network_request.authorize()

    dom = self.network_request.fetchDom(self.network_request.base_url + '/series/%s/seasons' % series_code)
    watched_episodes = self.watched_episodes(series_id)

    series_blocks = dom.find('div', {'class': 'serie-block'})
    episode_trs = series_blocks[0].find('tr')

    episode_list_items = []

    i = 0
    while (i < len(series_blocks)):
      episode_trs = series_blocks[i].find('tr')

      series_data = [
        series_id,
        series_code,
        'Season ' + str(len(series_blocks) - i),
        u'Сезон ' + str(len(series_blocks) - i),
        0,
        0
      ]
      episode_list_items.append(Serie(*series_data).episodes_list_item())

      for episode_tr in episode_trs:
        if 'not-available' not in episode_tr.classes:
          season_number, episode_number = self.episode_numbers(episode_tr.find('td', {'class': 'beta'}))
          if season_number == 999:
            continue

          title_en, title_ru = self.episode_titles(episode_tr.find('td', {'class': 'gamma'}))

          episode_watched = False
          if len(watched_episodes) > 0:
            episode_watched = self.episode_watched(series_id, season_number, episode_number, watched_episodes['data'])

          date_row = episode_tr.find('td', {'class': 'delta'}).text
          date = re.search('(Ru:\ )(\d{2}.\d{2}.\d{4})', date_row).group(2)

          rating = episode_tr.find('div', {'class': 'mark-green-box'}).text

          episode_data = [
            series_id,
            series_code,
            season_number,
            episode_number,
            title_en,
            title_ru,
            date,
            rating,
            episode_watched
          ]

          episode_list_items.append(Episode(*episode_data).list_item())

      i = i + 1

    return episode_list_items

  def episode_titles(self, dom):
    title_en = dom.find('span').text
    title_ru = re.search('([^>])(.*)(?=\<br)', dom.html).group(2).lstrip()
    return title_en, title_ru

  def episode_numbers(self, dom):
    numbers = re.findall('(\d+)', dom.text)
    if len(numbers) == 2:
      return numbers[0], numbers[1]
    else:
      return 999, 999

  def watched_episodes(self, series_id):
    data = {
      'act': 'serial',
      'type': 'getmarks',
      'id': series_id
    }
    response = self.network_request.fetchDom(url = self.network_request.post_url, data = data)
    parsed_response = json.loads(response.text)

    return parsed_response

  def episode_watched(self, series_id, season_number, episode_number, watched_episodes):
    separator = '-'
    serie_episode_id = separator.join((str(series_id), str(season_number), str(episode_number)))

    if serie_episode_id in watched_episodes:
      episode_watched = True
    else:
      episode_watched = False

    return episode_watched

  def get_torrent_links(self, series_id, season_number, episode_number):
    url = self.network_request.base_url + \
      '/v_search.php?c=%s&s=%s&e=%s' % (series_id, season_number, episode_number)

    dom = self.network_request.fetchDom(url)
    retr_url = dom.find('a').attr('href')

    dom = self.network_request.fetchDom(retr_url)
    links_list = dom.find('div', {'class': 'inner-box--list'})
    link_blocks = links_list.find('div', {'class': 'inner-box--item'})

    links = []
    for link_block in link_blocks:
      link_quality = link_block.find('div', {'class': 'inner-box--label'}).text
      links_list_row = link_block.find('div', {'class': 'inner-box--link sub'})
      links_href = links_list_row.find('a').attr('href')
      link_desc = link_block.find('div', {'class': 'inner-box--desc'}).text
      size = re.search('(\d+\.\d+)', link_desc).group(1)

      links.append(TorrentLink(Quality.find(link_quality), links_href, self.parse_size(size)))

    return links

  def parse_size(self, size):
    if len(size) == 4:
      return long(float(size) * 1024 * 1024 * 1024)
    else:
      return long(float(size) * 1024 * 1024)

  def mark_episode_watched(self, series_id, season_number, episode_number):
    separator = '-'
    serie_episode_id = separator.join((str(series_id), str(season_number), str(episode_number)))
    watched_episodes = self.watched_episodes(series_id)

    if len(watched_episodes) == 0:
      watched = False
    else:
      watched = self.episode_watched(series_id, season_number, episode_number, watched_episodes['data'])

    if not watched:
      data = {
        'act': 'serial',
        'type': 'markepisode',
        'val': serie_episode_id
      }
      self.network_request.fetchDom(url = self.network_request.post_url, data = data)

    return None
