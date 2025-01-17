import asyncio
import concurrent.futures
import gc
import itertools
import os
import random
import time
import typing
import typing as t
from urllib.parse import urljoin
from urllib.parse import urlparse
import cloudscraper

import aiofiles
import discord
import parsel
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from discord import app_commands
from discord.ext import commands
from readabilipy import simple_json_from_html_string

from cogs.admin import Admin
from cogs.library import Library
from cogs.termer import Termer
from cogs.translation import Translate
from core.bot import Raizel
from utils.handler import FileHandler
from utils.selector import CssSelector

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/75.0.3770.142 Safari/537.36"
}


class Crawler(commands.Cog):
    def __init__(self, bot: Raizel) -> None:
        self.titlecss = None
        self.chptitlecss = None
        self.urlcss = None
        self.bot = bot

    @staticmethod
    def easy(nums: int, links: str, css: str, chptitleCSS: str, scraper) -> t.Tuple[int, str]:
        response = None
        try:
            if scraper is not None:
                response = scraper.get(links, headers=headers, timeout=20)
            else:
                response = requests.get(links, headers=headers, timeout=20)
        except Exception as e:
            time.sleep(10)
            try:
                if scraper is not None:
                    response = scraper.get(links, headers=headers, timeout=20)
                else:
                    response = requests.get(links, headers=headers, timeout=20)
            except:
                print(e)
                return nums, f"\ncouldn't get connection to {links}\n"
        if response.status_code == 404:
            print("Response received as error status code 404")
            return nums, "\n----x---\n"
        response.encoding = response.apparent_encoding
        full = ""
        if '* ::text' == css or css is None or css.strip() == '':
            try:
                article = simple_json_from_html_string(response.text)
                text = article['plain_text']
                chpTitle = article['title']
                # print(chpTitle)
                full += str(chpTitle) + "\n\n"
                for i in text:
                    full += i['text'] + "\n"
            except:
                full = ""

        if full == "":
            html = response.text
            sel = parsel.Selector(html)
            text = sel.css(css).extract()

            if not chptitleCSS == "":
                try:
                    chpTitle = sel.css(chptitleCSS).extract_first()
                except:
                    chpTitle = None
                # print('chp' + str(chpTitle))
                if not chpTitle is None:
                    full += str(chpTitle) + "\n\n"
            # print(css)
            if text == []:
                return nums, ""
            if "ptwxz" in links:
                while text[0] != "GetFont();":
                    text.pop(0)
                text.pop(0)
            full = full + "\n".join(text)
        full = full + "\n---------------------xxx---------------------\n\n"
        if "uukanshu" in links:
            time.sleep(5)
        return nums, full

    def scrape(self, scraper, links: str):
        response = scraper.get(links, headers=headers, timeout=20)
        return response

    def direct(self, urls: t.List[str], novel: t.Dict[int, str], name: int, cloudscrape: bool) -> dict:
        if cloudscrape:
            scraper = cloudscraper.CloudScraper()
        else:
            scraper = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(self.easy, i, j, self.urlcss, self.chptitlecss, scraper)
                for i, j in enumerate(urls)
            ]
            for future in concurrent.futures.as_completed(futures):
                novel[future.result()[0]] = future.result()[1]
                try:
                    if self.bot.crawler[name] == "break":
                        return None
                except:
                    pass
                self.bot.crawler[name] = f"{len(novel)}/{len(urls)}"
            return novel

    async def getcontent(self, links: str, css: str, next_xpath, bot, tag, scraper):
        try:
            if scraper is not None:
                response = await self.bot.loop.run_in_executor(None, self.scrape, scraper, links)
                response.encoding = response.apparent_encoding
                soup = BeautifulSoup(response.text, "html.parser", from_encoding=response.encoding)
                if response.status_code == 404:
                    return ['error', links]
                # await asyncio.sleep(0.1)
            else:
                response = await bot.con.get(links)
                soup = BeautifulSoup(await response.read(), "html.parser", from_encoding=response.get_encoding())
                if response.status == 404:
                    return ['error', links]
            # response = requests.get(links, headers=headers, timeout=10)
        except:
            return ['error', links]

        # response.encoding = response.apparent_encoding
        # chp_html = response.text
        sel = parsel.Selector(str(soup))
        article = simple_json_from_html_string(str(soup))
        chpTitle = article['title']
        full_chp = ""
        if '* ::text' == css or css is None or css.strip() == '':
            text = article['plain_text']
            full_chp += str(chpTitle) + "\n\n"
            for i in text:
                full_chp += i['text'] + "\n"
        else:
            full_chp += str(chpTitle) + "\n\n"
            text = sel.css(css).extract()
            # print(css)
            if text == []:
                return ""
            full_chp = full_chp + "\n".join(text)
        try:
            if tag:
                raise Exception
            next_href = sel.xpath(next_xpath + '/@href').extract()[0]
            next_href = urljoin(links, next_href)
        except:
            try:
                # if css selector is given it will come here due to exception
                next_href = sel.css(next_xpath).extract_first()
                next_href = urljoin(links, next_href)
            except:
                next_href = None

        full_chp = full_chp + "\n---------------------xxx---------------------\n\n"

        return [full_chp, next_href]

    def xpath_soup(self, element):
        components = []
        child = element if element.name else element.parent
        for parent in child.parents:
            previous = itertools.islice(parent.children, 0, parent.contents.index(child))
            xpath_tag = child.name
            xpath_index = sum(1 for i in previous if i.name == xpath_tag) + 1
            components.append(xpath_tag if xpath_index == 1 else '%s[%d]' % (xpath_tag, xpath_index))
            child = parent
        components.reverse()
        return '/%s' % '/'.join(components)

    @commands.hybrid_command(help="Gives progress of novel crawling", aliases=["cp"])
    async def crawled(self, ctx: commands.Context) -> typing.Optional[discord.Message]:
        if ctx.author.id not in self.bot.crawler:
            return await ctx.send(
                "> **❌You have no novel deposited for crawling currently.**"
            )
        await ctx.send(f"> **🚄`{self.bot.crawler[ctx.author.id]}`**")

    async def cc_prog(self, msg: discord.Message, msg_content: str, author_id: int) -> typing.Optional[discord.Message]:
        value = 0
        while author_id in self.bot.crawler:
            await asyncio.sleep(10)
            if author_id not in self.bot.crawler:
                content = msg_content + f"\nProgress > **🚄`Completed`    {100}%**"
                msg = await msg.edit(content=content)
                return None
            try:
                if eval(self.bot.crawler[author_id]) < value:
                    content = msg_content + f"\nProgress > **🚄`Completed`    {100}%**"
                    msg = await msg.edit(content=content)
                    return None
                else:
                    value = eval(self.bot.crawler[author_id])
                    out = str(round(value * 100, 2))
            except Exception as e:
                print(e)
                out = ""
            content = msg_content + f"\nProgress > **🚄`{self.bot.crawler[author_id]}`    {out}%**"
            try:
                msg = await msg.edit(content=content)
            except:
                pass
        return

    @commands.hybrid_command(help="stops the tasks initiated by user", aliases=["st"])
    async def stop(self, ctx: commands.Context) -> typing.Optional[discord.Message]:
        if ctx.author.id not in self.bot.crawler and ctx.author.id not in self.bot.translator:
            return await ctx.send(
                "> **❌You have no tasks currently running.**"
            )
        if ctx.author.id in self.bot.crawler:
            self.bot.crawler[ctx.author.id] = "break"
        elif ctx.author.id in self.bot.translator:
            self.bot.translator[ctx.author.id] = "break"
        await ctx.send("> Added stop command to all tasks..")

    @commands.hybrid_command(
        help="Crawls other sites for novels. \nselector: give the css selector for the content page. It will try to auto select if not given\n Reverse: give any value if Table of Content is reversed in the given link(or if crawled novel needs to be reversed)")
    async def crawl(
            self, ctx: commands.Context, link: str = None, reverse: str = None, selector: str = None,
            cloudscrape: bool = False,
            translate_to: str = None,
            add_terms: str = None,
            max_chapters: int = None,
    ) -> typing.Optional[discord.Message]:
        if ctx.author.id in self.bot.crawler:
            return await ctx.reply(
                "> **❌You cannot crawl two novels at the same time.**"
            )
        if self.bot.app_status == "restart":
            return await ctx.reply(
                f"> Bot is scheduled to restart within 60 sec or after all current tasks are completed.. Please try after bot is restarted")
        if link is None:
            return await ctx.reply(f"> **❌Enter a link for crawling.**")
        allowed = self.bot.allowed
        next_sel = CssSelector.find_next_selector(link)
        if next_sel[0] is not None:
            return await ctx.reply(
                "> **Provided site is found in crawl_next available sites. This site doesn't have TOC page........ so proceed with /crawlnext or .tcrawlnext <first_chapter_link>**")
        msg = await ctx.reply('Started crawling please wait')
        num = 0
        for i in allowed:
            if i not in link:
                num += 1
        # if num == len(allowed):
        #     return await ctx.reply(
        #         f"> **❌We currently crawl only from {', '.join(allowed)}**"
        #     )
        if "69shu" in link and "txt" in link:
            link = link.replace("/txt", "")
            link = link.replace(".htm", "/")
        if ("krmtl.com" in link or "metruyencv.com" in link) and max_chapters is None:
            return await ctx.reply("> **Provide max_chapters value in slash command for this site to be crawled**")
        if "ptwxz" in link and "bookinfo" in link:
            link = link.replace("bookinfo", "html")
            link = link.replace(".html", "/")
        if link[-1] == "/" and "69shu" not in link and "uukanshu.cc" not in link and not num == len(allowed):
            link = link[:-1]
        # if "m.uuks" in link:
        #     link = link.replace("m.", "")
        if "novelsemperor" in link or "novelsknight.com" in link:
            reverse = "true"
        if "www.xklxsw.com/" in link:
            link = link.replace("www", "m")
        try:
            res = await self.bot.con.get(link)
        except Exception as e:
            print(e)
            await msg.delete()
            return await ctx.send("We couldn't connect to the provided link. Please check the link")
        novel = {}
        if cloudscrape:
            scraper = cloudscraper.CloudScraper()  # CloudScraper inherits from requests.Session
            response = scraper.get(link)
            soup = BeautifulSoup(response.text, "html.parser", from_encoding=response.encoding)
            soup1 = soup
        else:
            soup = BeautifulSoup(await res.read(), "html.parser", from_encoding=res.get_encoding())
            data = await res.read()
            soup1 = BeautifulSoup(data, "lxml", from_encoding=res.get_encoding())

        self.titlecss = CssSelector.findchptitlecss(link)
        maintitleCSS = self.titlecss[0]
        try:
            title_name = str(soup1.select(maintitleCSS)[0].text)
            if title_name == "" or title_name is None:
                raise Exception
        except Exception as e:
            print(e)
            try:
                title_name = ""
                response = requests.get(link, headers=headers)
                response.encoding = response.apparent_encoding
                html = response.text
                sel = parsel.Selector(html)
                try:
                    title_name = sel.css(maintitleCSS + " ::text").extract_first()
                except Exception as e:
                    print("error at 200" + str(e))
                if title_name.strip() == "" or title_name is None:
                    title_name = sel.css("title ::text").extract_first()
                # print(title)

            except Exception as ex:
                print(ex)
                title_name = f"{ctx.author.id}_crl"
        # print('titlename'+title_name)
        self.chptitlecss = self.titlecss[1]

        if selector is None:
            self.urlcss = CssSelector.findURLCSS(link)
        else:
            if not '::text' in selector:
                selector = selector + " ::text"
            self.urlcss = selector
        # print('translated' + title_name)
        # print(self.urlcss)
        name = str(link.split("/")[-1].replace(".html", ""))
        # name=name.replace('all','')
        urls = []
        frontend_part = link.replace(f"/{name}", "").split("/")[-1]
        frontend = link.replace(f"/{name}", "").replace(f"/{frontend_part}", "")
        if "69shu" in link:
            urls = [
                f"{j}"
                for j in [str(i.get("href")) for i in soup.find_all("a")]
                if name in j and "http" in j
            ]
        elif "ptwxz" in link:
            frontend = link + "/"
            urls = [
                f"{frontend}{j}"
                for j in [str(i.get("href")) for i in soup.find_all("a")]
                if "html" in j
                   and "txt" not in j
                   and "http" not in j
                   and "javascript" not in j
                   and "modules" not in j
            ]
        elif "uukanshu.cc" in link:
            frontend = "https://uukanshu.cc/"
            urls = [
                f"{frontend}{j}"
                for j in [str(i.get("href")) for i in soup.find_all("a")]
                if "/book" in j and name in j and "txt" not in j
            ]
        else:
            urls = [
                f"{frontend}{j}"
                for j in [str(i.get("href")) for i in soup.find_all("a")]
                if name in j and ".html" in j and "txt" not in j
            ]
        if urls == []:
            if "sj.uukanshu" in link:
                surl = "/sj.uukanshu.com/"
                urls = [
                    f"{frontend}{surl}{j}"
                    for j in [str(i.get("href")) for i in soup.find_all("a")]
                    if "read.aspx?tid" in j and "txt" not in j
                ]
            # elif "uuks" in link:
            #     # print(frontend)
            #     # name=name.replace('all','')
            #     # print(name)
            #     urls = [
            #         f"{frontend}{j}"
            #         for j in [str(i.get("href")) for i in soup.find_all("a")]
            #         if "/b/" in j and "txt" not in j
            #     ]
            # print(urls)
            elif "t.uukanshu" in link:
                surl = "/t.uukanshu.com/"
                urls = [
                    f"{frontend}{surl}{j}"
                    for j in [str(i.get("href")) for i in soup.find_all("a")]
                    if "read.aspx?tid" in j and "txt" not in j
                ]
        if (
                "uukanshu" in link
                and "sj.uukanshu" not in link
                and "t.uukanshu" not in link
                and "uukanshu.cc" not in link
                and not urls == []
        ):
            urls = urls[::-1]
        if urls == [] or num == len(allowed) or len(urls) < 30:
            urls = [
                f"{j}"
                for j in [str(i.get("href")) for i in soup.find_all("a")]
                if name in j and "txt" not in j
            ]
            host = urlparse(link).netloc
            if urls == [] or len(urls) < 30:
                urls = [
                    f"{j}"
                    for j in [str(i.get("href")) for i in soup.find_all("a")]
                    if "txt" not in j
                ]
            utemp = []
            for url in urls:
                utemp.append(urljoin(link, url))
            urls = [u for u in utemp if host in u]
        if urls == [] or len(urls) < 30:
            if link[-1] == '/':
                link = link[:-1]

            try:
                response = requests.get(link, headers=headers, timeout=20)
            except:
                print('error')
            response.encoding = response.apparent_encoding
            html = response.text
            sel = parsel.Selector(html)
            urls = [
                f"{j}"
                for j in sel.css('a ::attr(href)').extract()
                if name in j and "txt" not in j
            ]
            host = urlparse(link).netloc
            if urls == [] or len(urls) < 30:
                urls = [
                    f"{j}"
                    for j in sel.css('a ::attr(href)').extract()
                    if "txt" not in j
                ]

            utemp = []
            for url in urls:
                utemp.append(urljoin(link, url))
            urls = [u for u in utemp if host in u]
            # print(urls)
            title_name = sel.css(maintitleCSS + " ::text").extract_first()
            # print(urls)
        if urls == [] or len(urls) < 30:
            scraper = cloudscraper.CloudScraper()  # CloudScraper inherits from requests.Session
            response = scraper.get(link)
            soup = BeautifulSoup(response.text, "html.parser", from_encoding=response.encoding)
            urls = [
                f"{j}"
                for j in [str(i.get("href")) for i in soup.find_all("a")]
                if name in j and "txt" not in j
            ]
            host = urlparse(link).netloc
            if urls == [] or len(urls) < 30:
                urls = [
                    f"{j}"
                    for j in [str(i.get("href")) for i in soup.find_all("a")]
                    if "txt" not in j
                ]
            utemp = []
            for url in urls:
                utemp.append(urljoin(link, url))
            urls = [u for u in utemp if host in u]
            if len(urls) > 30:
                cloudscrape = True
                await ctx.send("Cloudscraper is turned on as cloudflare is detected", delete_after=5)
            try:
                title_name = str(soup.select(maintitleCSS)[0].text)
            except:
                title_name = "None"
        if "krmtl.com" in link:
            urls = []
            for i in range(1, max_chapters + 1):
                temp_link = link + "/" + str(i)
                urls.append(temp_link)
        if "metruyencv.com" in link:
            urls = []
            for i in range(1, max_chapters+1):  #https://metruyencv.com/truyen/tu-la-vu-than
                temp_link = link+ "/chuong-"+ str(i)
                urls.append(temp_link)
        if len(urls) < 30:
            return await ctx.reply(
                f"> ❌Provided link only got **{str(len(urls))}** links in the page.Check if you have provided correct Table of contents url. If there is no TOC page try using /crawlnext with first chapter and required urls"
            )
        if 'b.faloo' in link or 'wap.faloo' in link:
            urls = urls[:200]
        if reverse is not None:
            urls.reverse()
        if max_chapters is not None:
            urls = urls[:max_chapters]
        for tag in ['/', '\\', '!', '<', '>', "'", '"', ':', ";", '?', '|', '*', ';', '\r', '\n', '\t', '\\\\']:
            title_name = title_name.replace(tag, '')
        title_name = title_name.replace('_', ' ')
        original_Language = FileHandler.find_language(text="title_name " + title_name, link=link)
        if title_name == "" or title_name == "None" or title_name is None:
            title = f"{ctx.author.id}_crl"
            title_name = link
        else:
            if original_Language == 'english':
                title = str(title_name[:100])
            else:
                title = ""
                try:
                    title = GoogleTranslator(
                        source="auto", target="english"
                    ).translate(title_name).strip()
                except:
                    pass
                title_name = title + "__" + title_name
                title = str(title[:100])
        novel_data = await self.bot.mongo.library.get_novel_by_name(title_name.split('__')[0])
        # print(title_name)
        if novel_data is not None:
            name_lib_check = False
            novel_data = list(novel_data)
            ids = []
            for n in novel_data:
                ids.append(n._id)
                org_str = ''.join(e for e in title.split('__')[0] if e.isalnum())
                lib_str = ''.join(e for e in n.title if e.isalnum())
                if title.strip('__')[0] in n.title or org_str in lib_str:
                    name_lib_check = True
            if True:
                ids = ids[:20]
                ctx.command = await self.bot.get_command("library search").callback(Library(self.bot), ctx,
                                                                                    title_name.split('__')[0], None,
                                                                                    None,
                                                                                    None, None, None, None, None, None,
                                                                                    False, "size", 20)
                if len(ids) < 5 or name_lib_check:
                    await ctx.send("**Please check from above library**", delete_after=20)
                    await asyncio.sleep(15)
                for l in ["bixiange", "trxs", "txt520", "powanjuan", "tongrenquan", "jpxs"]:
                    if l in link and name_lib_check:
                        await ctx.send("Novel is already in our library. if its not ping Admin")
                        return None
                    else:
                        await asyncio.sleep(1)
                chk_msg = await ctx.send(embed=discord.Embed(
                    description=f"This novel **{title}** is already in our library with ids **{ids.__str__()}**...use arrow marks  in above  to navigate...  \n\nIf you want to continue crawling react with 🇳 \n\n**Note : Some files are in docx format, so file size maybe half the size of txt. and try to minimize translating if its already in library**"))
                await chk_msg.add_reaction('🇾')
                await chk_msg.add_reaction('🇳')

                def check(reaction, user):
                    return reaction.message.id == chk_msg.id and (
                            str(reaction.emoji) == '🇾' or str(reaction.emoji) == '🇳') and user == ctx.author

                try:
                    res = await self.bot.wait_for(
                        "reaction_add",
                        check=check,
                        timeout=16.0,
                    )
                except asyncio.TimeoutError:
                    print(' Timeout error')
                    try:
                        os.remove(f"{ctx.author.id}.txt")
                    except:
                        pass
                    await ctx.send("No response detected. ", delete_after=5)
                    await chk_msg.delete()
                    return None
                else:
                    await ctx.send("Reaction received", delete_after=10)
                    if str(res[0]) == '🇳':
                        msg = await ctx.reply("Reaction received.. please wait")
                    else:
                        await ctx.send("Reaction received", delete_after=10)
                        try:
                            os.remove(f"{ctx.author.id}.txt")
                        except:
                            pass
                        await chk_msg.delete()
                        return None
        if ctx.author.id in self.bot.crawler:
            return await ctx.reply(
                "> **❌You cannot crawl two novels at the same time.**"
            )
        no_tries = 0
        while len(asyncio.all_tasks()) >= 10:
            no_tries = no_tries + 1
            try:
                msg = await msg.edit(content="> **Currently bot is busy.Please wait some time**")
            except:
                pass
            await asyncio.sleep(10)
            if no_tries >= 5:
                self.bot.translator = {}
                self.bot.crawler = {}
                if len(self.bot.crawler) < 3:
                    break
                await asyncio.sleep(10)
        try:
            self.bot.crawler[ctx.author.id] = f"0/{len(urls)}"
            msg_content = f"> **:white_check_mark: Started Crawling the novel --  📔   {title_name.split('__')[0].strip()}.**"
            msg = await msg.edit(
                content=msg_content)
            asyncio.create_task(self.cc_prog(msg, msg_content, ctx.author.id))
            book = await self.bot.loop.run_in_executor(
                None, self.direct, urls, novel, ctx.author.id, cloudscrape,
            )
            if book is None:
                return await ctx.reply("Crawling stopped")
            parsed = {k: v for k, v in sorted(book.items(), key=lambda item: item[0])}
            whole = [i for i in list(parsed.values())]
            whole.insert(0, "\nsource : " + str(link) + "\n\n" + str(title_name.split('__')[0]) + "\n\n")
            text = "\n".join(whole)
            title = title[:100]
            async with aiofiles.open(f"{title}.txt", "w", encoding="utf-8") as f:
                await f.write(text)
            download_url = await FileHandler().crawlnsend(ctx, self.bot, title, title_name, original_Language)
        except Exception as e:
            await ctx.send("> Error occurred .Please report to admin +\n" + str(e))
            raise e
        finally:
            try:
                del text
                del whole
                del parsed
            except Exception as e:
                print("error")
                print(e)
            try:
                gc.collect()
            except:
                print("error in garbage collection")
            try:
                del self.bot.crawler[ctx.author.id]
                self.bot.titles.append(name)
                self.bot.titles = random.sample(self.bot.titles, len(self.bot.titles))
            except:
                pass
            if translate_to is None and add_terms is None:
                try:
                    if self.bot.translation_count >= 20 or self.bot.crawler_count >= 20:
                        await ctx.reply(
                            "> **Bot will be Restarted when the bot is free due to max limit is reached.. Please be patient")
                        chan = self.bot.get_channel(
                            991911644831678484
                        ) or await self.bot.fetch_channel(991911644831678484)
                        msg_new2 = await chan.fetch_message(1052750970557308988)
                        context_new2 = await self.bot.get_context(msg_new2)
                        asyncio.create_task(
                            self.bot.get_command("restart").callback(Admin(self.bot), context_new2))
                except:
                    pass
        if (
                translate_to is not None or add_terms is not None) and download_url is not None and not download_url.strip() == "":
            if translate_to is None:
                translate_to = "english"
            if translate_to not in self.bot.all_langs and original_Language not in ["english", "en"]:
                translate_to = "english"
            if add_terms is not None:
                ctx.command = await self.bot.get_command("termer").callback(Termer(self.bot), ctx, add_terms,
                                                                            download_url,
                                                                            None,
                                                                            None,
                                                                            translate_to, title_name[:100])
            else:
                ctx.command = await self.bot.get_command("translate").callback(Translate(self.bot), ctx, download_url,
                                                                               None,
                                                                               None,
                                                                               translate_to, title_name[:100])

    @commands.hybrid_command(
        help="Clears any stagnant novels which were deposited for crawling."
    )
    async def cclear(self, ctx: commands.Context):
        if ctx.author.id in self.bot.crawler:
            del self.bot.crawler[ctx.author.id]
        files = os.listdir()
        for i in files:
            if str(ctx.author.id) in str(i) and "crawl" in i:
                os.remove(i)
        await ctx.reply("> **✔Cleared all records.**")

    @commands.hybrid_command(
        help="Crawls if given 1st,2nd(or selector) and lastpage(or maxchps).use it when there is no TOC page")
    async def crawlnext(
            self, ctx: commands.Context, firstchplink: str, secondchplink: str = None, lastchplink: str = None,
            nextselector: str = None, noofchapters: int = None,
            cssselector: str = None, cloudscrape: bool = False
    ) -> typing.Optional[discord.Message]:
        if ctx.author.id in self.bot.crawler:
            return await ctx.reply(
                "> **❌You cannot crawl two novels at the same time.**"
            )
        if self.bot.app_status == "restart":
            return await ctx.reply(
                f"> Bot is scheduled to restart within 60 sec or after all current tasks are completed.. Please try after bot is restarted")
        title_css = "title"
        if nextselector is None:
            nextsel = CssSelector.find_next_selector(firstchplink)
            if nextsel[0] is not None:
                nextselector = nextsel[0]
                title_css = nextsel[1]
                secondchplink = None
                cloudscrape = True
            if "fannovels.com" in firstchplink or "xindingdianxsw.com" in firstchplink or "longteng788.com" in firstchplink or "75zw.com" in firstchplink or "longteng788.com" in firstchplink or "m.akshu8.com" in firstchplink or "www.wnmtl.org" in firstchplink:
                cloudscrape = False
        if secondchplink is None and nextselector is None:
            return await ctx.send("You must give second chapter link or next page css selector")
        msg = await ctx.send("Crawling will be started soon")
        if cssselector:
            css = cssselector
            if '::text' not in css:
                css += ' ::text'
        else:
            css = CssSelector.findURLCSS(firstchplink)
        if noofchapters is None:
            noofchapters = 3000
        try:
            if cloudscrape:
                scraper = cloudscraper.CloudScraper()
                response = scraper.get(firstchplink, headers=headers, timeout=20)
                await asyncio.sleep(0.25)
            else:
                scraper = None
                response = requests.get(firstchplink, headers=headers, timeout=20)
        except Exception as e:
            print(e)
            return await ctx.reply(
                "> Couldn't connect to the provided link.... Please check the link or try with cloudscraper true")
        if response.status_code == 404:
            return await ctx.reply("> Provided link gives 404 error... Please check the link")
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.content, 'html5lib', from_encoding=response.encoding)
        htm = response.text
        sel = parsel.Selector(htm)
        sel_tag = False
        if nextselector is not None:

            sel_tag = True
            if '::attr(href)' not in nextselector:
                nextselector += ' ::attr(href)'
            # print(nextselector)
            path = nextselector
        else:

            urls = sel.css('a ::attr(href)').extract()

            psrt = ''
            for url in urls:
                full_url = urljoin(firstchplink, url)
                if full_url == secondchplink:
                    psrt = url
            if psrt == '':
                return await ctx.send(
                    "We couldn't find the selector for next chapter. Please check the links or provide the css selector or check with turning on cloudscrape as true")
            href = [i for i in soup.find_all("a") if i.get("href") == psrt]
            # print(href)
            path = self.xpath_soup(href[0])

        title = sel.css(f'{title_css} ::text').extract_first()
        if title is None or str(title).strip() == "":
            print(f"title empty {title}")
            title = sel.css(f'title ::text').extract_first()
        chp_count = 1
        # print(title)
        current_link = firstchplink
        full_text = "Source : " + firstchplink + '\n\n'
        no_of_tries = 0
        original_Language = FileHandler.find_language("title_name " + title)
        if title is None or str(title).strip() == "" or title == "None":
            title = f"{ctx.author.id}_crl"
            title_name = firstchplink
        else:
            title_name = title
            if original_Language == 'english':
                title = str(title[:100])
            else:
                try:
                    title = GoogleTranslator(
                        source="auto", target="english"
                    ).translate(title).strip()
                except:
                    pass
                title_name = title + "__" + title_name
                try:
                    title = str(title[:100])
                except:
                    pass
            for tag in ['/', '\\', '<', '>', "'", '"', ':', ";", '?', '|', '*', ';', '\r', '\n', '\t', '\\\\']:
                title = title.replace(tag, '')
        novel_data = await self.bot.mongo.library.get_novel_by_name(title_name.split('__')[0])
        # print(title_name)
        if novel_data is not None:
            novel_data = list(novel_data)
            name_lib_check = False
            ids = []
            for n in novel_data:
                ids.append(n._id)
                if title_name.strip('__')[0] in n.title:
                    name_lib_check = True
            if True:
                ids = ids[:20]
                ctx.command = await self.bot.get_command("library search").callback(Library(self.bot), ctx,
                                                                                    title_name.split('__')[0], None,
                                                                                    None,
                                                                                    None, None, None, None, None, None,
                                                                                    False, "size", 20)
                if len(ids) < 5 or name_lib_check:
                    await ctx.send("**Please check from above library**", delete_after=20)
                    await asyncio.sleep(15)
                chk_msg = await ctx.send(embed=discord.Embed(
                    description=f"This novel **{title}** is already in our library with ids **{ids.__str__()}**...use arrow marks in above to navigate...\nIf you want to continue crawling react with 🇳 \n\n**Note : Some files are in docx format, so file size maybe half the size of txt. and try to minimize translating if its already in library**"))
                await chk_msg.add_reaction('🇾')
                await chk_msg.add_reaction('🇳')

                def check(reaction, user):
                    return reaction.message.id == chk_msg.id and (
                            str(reaction.emoji) == '🇾' or str(reaction.emoji) == '🇳') and user == ctx.author

                try:
                    res = await self.bot.wait_for(
                        "reaction_add",
                        check=check,
                        timeout=16.0,
                    )
                except asyncio.TimeoutError:
                    print(' Timeout error')
                    try:
                        os.remove(f"{ctx.author.id}.txt")
                    except:
                        pass
                    await ctx.send("No response detected.", delete_after=5)
                    await chk_msg.delete()
                    return None
                else:
                    await ctx.send("Reaction received", delete_after=10)
                    if str(res[0]) == '🇳':
                        msg = await ctx.reply("Reaction received.. please wait")
                    else:
                        await ctx.send("Reaction received", delete_after=10)
                        try:
                            os.remove(f"{ctx.author.id}.txt")
                        except:
                            pass
                        await chk_msg.delete()
                        return None
        msg = await msg.edit(content=f"> :white_check_mark:  Started crawling from 📔 {title_name}")
        crawled_urls = []
        repeats = 0
        try:
            self.bot.crawler[ctx.author.id] = f"0/{noofchapters}"
            for i in range(1, noofchapters):
                try:
                    if self.bot.crawler[ctx.author.id] == "break":
                        return await ctx.send("> **Stopped Crawling...**")
                except:
                    break
                self.bot.crawler[ctx.author.id] = f"{i}/{noofchapters}"
                if current_link in crawled_urls:
                    repeats += 1
                if current_link in crawled_urls and repeats > 5:
                    if i >= 30:
                        break
                    del self.bot.crawler[ctx.author.id]
                    if current_link == firstchplink and i < 10:
                        return await ctx.reply(
                            'Error occurred . Some problem in the site. please try with second and third chapter or give valid css selector for next page button')
                    if sel_tag:
                        return await ctx.send(" There is some problem with the provided selector")
                    else:
                        return await ctx.send(" There is some problem with the detected selector")
                if "readwn" in current_link or "wuxiax.co" in current_link or "novelmt.com" in current_link or "fannovels.com" in current_link:
                    await asyncio.sleep(1.3)
                    if i % 25 == 0:
                        await asyncio.sleep(4.1)
                try:
                    output = await self.getcontent(current_link, css, path, self.bot, sel_tag, scraper)
                    chp_text = output[0]
                except Exception as e:
                    if i <= 10:
                        print(e)
                        return await ctx.send(f"Error occurred in crawling \n Error occurred at {current_link}")
                    else:
                        print("error occured at " + current_link + str(e))
                        break

                # print(i)
                if chp_text == 'error':
                    no_of_tries += 1
                    chp_text = ''
                    if no_of_tries > 30:
                        # await msg.delete()
                        del self.bot.crawler[ctx.author.id]
                        return await ctx.send('Error occurred when crawling. Please Report to my developer')
                full_text += chp_text
                # print(current_link)
                if current_link == lastchplink or i >= noofchapters or output[1] is None:
                    print('break')
                    break
                chp_count += 1
                crawled_urls.append(current_link)
                current_link = output[1]
                if random.randint(0, 65) == 10 or chp_count % 100 == 0:
                    try:
                        msg = await msg.edit(
                            content=f"> :white_check_mark:  Started crawling from 📔 {title_name}\n**Crawled {chp_count} pages**")
                    except:
                        pass
                    await asyncio.sleep(0.5)

            with open(title + '.txt', 'w', encoding='utf-8') as f:
                f.write(full_text)
            await ctx.send(f"> **crawled {i} chapters**")
            return await FileHandler().crawlnsend(ctx, self.bot, title, title_name, original_Language)
        except Exception as e:
            await ctx.send("> Error occurred .Please report to admin +\n" + str(e))
            raise e
        finally:
            try:
                del full_text
            except:
                pass
            try:
                del self.bot.crawler[ctx.author.id]
            except:
                pass
            try:
                gc.collect()
            except:
                print("error in garbage collection")

    @crawl.autocomplete("translate_to")
    async def translate_complete(
            self, inter: discord.Interaction, language: str
    ) -> list[app_commands.Choice]:
        lst = [i for i in self.bot.all_langs if language.lower() in i.lower()][:25]
        return [app_commands.Choice(name=i, value=i) for i in lst]

    @crawl.autocomplete("add_terms")
    async def translate_complete(
            self, inter: discord.Interaction, term: str
    ) -> list[app_commands.Choice]:
        lst = [
                  "naruto",
                  "one-piece",
                  "pokemon",
                  "mixed",
                  "prince-of-tennis",
                  "marvel",
                  "dc",
                  "xianxia",
              ] + list(map(str, range(1, 8)))
        return [app_commands.Choice(name=i, value=i) for i in lst]


async def setup(bot: Raizel) -> None:
    await bot.add_cog(Crawler(bot))
