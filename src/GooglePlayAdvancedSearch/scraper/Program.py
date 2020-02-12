#!/usr/bin/env python3

import io
import re
import scrapy
import sys
import urllib.parse as urlParse

from scrapy.crawler import CrawlerProcess
from json import loads as jsonLoads

sys.path.append("../..")
from GooglePlayAdvancedSearch.Models import AppItem


class AppInfoSpider(scrapy.Spider):
	name = "brickset_spider"

	def __init__(self):
		try:
			index = sys.argv.index("-p")
			self.targetAppIds = sys.argv[index + 1].split(',')
		except:
			self.targetAppIds = ['com.mojang.minecraftpe', 'com.sega.sonic1px', 'com.tencent.mm',
								 'com.freecamchat.liverandomchat', 'com.matchdating.meetsingles34']

	def start_requests(self):
		for _url in ['https://play.google.com/store/apps/details?hl=en&id=' + id for id in self.targetAppIds]:
			yield scrapy.Request(url=_url, callback=self.parse)

	def parse(self, response):
		appInfo = AppItem()
		appInfo['id'] = urlParse.parse_qs(urlParse.urlparse(response.url).query)['id'][0]

		h1 = response.css("h1[itemprop=name]")
		appInfo['appName'] = h1.css("*::text").get()

		parentBox = h1.xpath('../..')
		c1 = parentBox.css("a[itemprop=genre]")
		appInfo['categories'] = c1.css("*::text").getall()
		appInfo['inAppPurchases'] = parentBox.xpath("div[text()[contains(.,'Offers in-app purchases')]]").get() is not None
		appInfo['containsAds'] = parentBox.xpath("div[text()[contains(.,'Contains Ads')]]").get() is not None
		try:
			# the first match is the rating box.
			ariaLabel = response.css('c-wiz div[aria-label][role=img]::attr(aria-label)').get()
			appInfo['rating'] = float(re.search(r'\d\.\d', ariaLabel)[0])
		except:
			appInfo['rating'] = 0

		try:
			ariaLabel_review = parentBox.css('span[aria-label]::attr(aria-label)').get()
			appInfo['num_reviews'] = int(ariaLabel_review.split(' ')[0].replace(',', ''))
		except:
			appInfo['num_reviews'] = None

		ariaLabel_fee = parentBox.xpath('following-sibling::*').css('span button[aria-label]::attr(aria-label)').get()
		if (ariaLabel_fee == "Install"):
			appInfo['install_fee'] = 0
		else:
			appInfo['install_fee'] = float(re.search(r'\d+\.\d*', ariaLabel_fee)[0])

		ariaLabel_icon = response.css("img[itemprop=image][alt='Cover art']::attr(src)").get()
		print(ariaLabel_icon)
		appInfo['app_icon'] = ariaLabel_icon

		r = scrapy.FormRequest(r'https://play.google.com/_/PlayStoreUi/data/batchexecute?rpcids=xdSrCf&hl=en',
							   headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
							   formdata={'f.req': r'[[["xdSrCf","[[null,[\"' + appInfo['id'] + r'\",7],[]]]",null,"1"]]]'},
							   # not use cb_kwargs because it's only passed to callback, no errback.
							   meta={'appInfo': appInfo},
							   callback=self.permissions_retrieved,
							   errback=self.errback)
		yield r

	def errback(self, failure):
		appInfo = failure.request.meta['appInfo']
		print(f'appName={appInfo.appName},  rating={appInfo.rating}, inAppPurchases={appInfo.inAppPurchases}, categories={appInfo["categories"]},'
			  f'containsAds={appInfo.containsAds}, number of reviews={appInfo["num_reviews"]}, permissions=Not available')

	# print(failure)

	def permissions_retrieved(self, response):
		appInfo = response.meta['appInfo']
		package = jsonLoads(response.text[response.text.index('\n') + 1:])
		permissionData = jsonLoads(package[0][2])

		permissions = []

		# permissionData may have
		# nothing, or
		# grouped permissions, or
		# grouped permissions + other permissions, or
		# grouped permissions + other permissions + miscellaneous permissions

		# permissionData[0] is grouped permissions.
		if len(permissionData) > 0:
			if (permissionData[0]):
				for g in permissionData[0]:
					# permission group may be empty.
					if (not g):
						continue
					for p in g[2]:
						permissions.append(p[1])

		# permissionData[1] is other permissions.
		if len(permissionData) > 1:
			for p in permissionData[1][0][2]:
				permissions.append(p[1])

		# permissionData[2] is miscellaneous permissions.
		if len(permissionData) > 2:
			for p in permissionData[2]:
				permissions.append(p[1])

		if len(permissionData) > 3:
			print('Unknown data in permission block.\npermissionData={}'.format(permissionData), file=sys.stderr)

		print(f'appName={appInfo["appName"]},  rating={appInfo["rating"]}, inAppPurchases={appInfo["inAppPurchases"]}, containsAds={appInfo["containsAds"]}, '
		      f'categories={appInfo["categories"]}, number of reviews={appInfo["num_reviews"]},  install_fee={appInfo["install_fee"]},'
			  f'app_icon={appInfo["app_icon"]}')
		print(f'permissions={permissions}')
		appInfo['permissions'] = permissions
		yield appInfo


if '--pytest' in sys.argv and sys.platform == 'win32' and sys.stdout.encoding == 'cp936':
	# com.sega.sonic1px has unicode characters. Without this fix, if run in pytest, the print statement throws exception.
	sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf8')

process = CrawlerProcess(settings={
	# don't have to output log to the console.
	# https://docs.scrapy.org/en/latest/topics/settings.html#log-enabled
	# 'LOG_ENABLED': False
	'LOG_LEVEL': 'WARNING',
	'ITEM_PIPELINES': {
		'pipeline.DatabasePipeline': 300,
		# 'myproject.pipelines.JsonWriterPipeline': 800 #another pipline
	}
})

process.crawl(AppInfoSpider)
process.start()  # the script will block here until the crawling is finished