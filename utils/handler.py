import datetime
import os
import typing
import zipfile

import aiofiles
import chardet
import discord
import docx
from discord.ext import commands
from textblob import TextBlob

from core.bot import Raizel
from core.views.linkview import LinkView
from databases.data import Novel


class FileHandler:

    ENCODING: list[str] = ["utf-8", "cp936", "utf-16", "cp949"]
    TOTAL: int = len(ENCODING)

    @staticmethod
    def get_tags(text: str) -> list[str]:
        text = TextBlob(text)
        return list(set(text.noun_phrases))

    @staticmethod
    def checkname(name):
        spl = name.split("_")
        segment = 0
        for t in spl:
            if t[:-1].isalpha() and len(t) > 2:
                if len(t) > 4 or segment == 2:
                    return True
                else:
                    segment += 1
        return False

    @staticmethod
    async def docx_to_txt(ctx: commands.Context, file_type: str):
        await ctx.reply(
            "> **✔Docx file detected please wait while we finish converting.**"
        )
        await ctx.typing()
        doc = docx.Document(f"{ctx.author.id}.{file_type}")
        string = "\n".join([para.text for para in doc.paragraphs])
        async with aiofiles.open(f"{ctx.author.id}.txt", "w", encoding="utf-8") as f:
            await f.write(string)
        os.remove(f"{ctx.author.id}.docx")

    async def read_file(
        self, ctx: commands.Context
    ) -> typing.Union[str, discord.Message]:
        novel = None
        for i, j in enumerate(self.ENCODING):
            try:
                async with aiofiles.open(f"{ctx.author.id}.txt", "r", encoding=j) as f:
                    novel = await f.read()
                    break
            except UnicodeDecodeError:
                if i == self.TOTAL - 1:
                    try:
                        await ctx.send(
                            "> **✔Encoding not in db trying to auto detect please be patient.**"
                        )
                        async with aiofiles.open(f"{ctx.author.id}.txt", "rb") as f:
                            novel = await f.read()
                        async with aiofiles.open(
                            f"{ctx.author.id}.txt",
                            "r",
                            encoding=chardet.detect(novel[:500])["encoding"],
                            errors="ignore",
                        ) as f:
                            novel = await f.read()
                    except Exception as e:
                        print(e)
                        return await ctx.reply(
                            "> **❌Currently we are only translating korean and chinese.**"
                        )
        return novel

    @staticmethod
    def get_headers(response) -> str:
        string = "".join(
            [
                i
                for i in response.headers["Content-Disposition"].split(".")[-1]
                if i.isalnum()
            ]
        )
        return string

    async def distribute(
        self, bot: Raizel, ctx: commands.Context, name: str, language: str
    ) -> None:
        download_url = None
        if (size := os.path.getsize(f"{ctx.author.id}.txt")) > 8 * 10**6:
            try:
                with zipfile.ZipFile(f"{ctx.author.id}.zip", "w") as jungle_zip:
                    jungle_zip.write(
                        f"{ctx.author.id}.txt", compress_type=zipfile.ZIP_DEFLATED
                    )
                filelnk = bot.drive.upload(filepath=f"{ctx.author.id}.zip")
                view = LinkView({"Novel": [filelnk.url, "📔"]})
                await ctx.reply(
                    f"> **✔{ctx.author.mention} your novel {name} is ready.**",
                    view=view,
                )
                channel = bot.get_channel(1005668482475643050)
                user = str(ctx.author)
                await channel.send(
                    f"> {name.replace('_',' ')} \nuploaded by {user} language: {language}",
                    view=view,
                )
                download_url = filelnk.url
            except Exception as e:
                print(e)
                await ctx.reply(
                    "**Sorry your file was too big please split it and try again.**"
                )
            os.remove(f"{ctx.author.id}.zip")
        else:
            file = discord.File(f"{ctx.author.id}.txt", f"{name}.txt")
            await ctx.reply("**🎉Here is your translated novel**", file=file)
            channel = bot.get_channel(1005668482475643050)
            user = str(ctx.author)
            msg = await channel.send(
                f'> {name.replace("_"," ")} \nUploaded by {user} language: {language}',
                file=discord.File(f"{ctx.author.id}.txt", f"{name}.txt"),
            )
            download_url = msg.attachments[0].url
        if download_url:
            novel_data = [
                await bot.mongo.library.next_number,
                name,
                "",
                0,
                language,
                self.get_tags(name),
                download_url,
                size,
                ctx.author.id,
                datetime.datetime.utcnow().timestamp(),
            ]
            data = Novel(*novel_data)
            await bot.mongo.library.add_novel(data)
        os.remove(f"{ctx.author.id}.txt")
        del bot.translator[ctx.author.id]

    async def crawlnsend(
        self, ctx: commands.Context, bot: Raizel, title: str, title_name: str
    ) -> None:
        download_url = None
        if (size := os.path.getsize(f"{title}.txt")) > 8 * 10**6:
            try:
                with zipfile.ZipFile(f"{title}.zip", "w") as jungle_zip:
                    jungle_zip.write(f"{title}.txt", compress_type=zipfile.ZIP_DEFLATED)
                filelnk = bot.drive.upload(filepath=f"{title}.zip")
                view = LinkView({"Novel": [filelnk.url, "📔"]})
                await ctx.reply(
                    f"> **✔{ctx.author.mention} your novel {title_name} is ready.**",
                    view=view,
                )
                download_url = filelnk.url
            except Exception as e:
                print(e)
                await ctx.reply("> **❌Sorry the file is too big to send.**")
            os.remove(f"{title}.zip")
        else:
            file = discord.File(f"{title}.txt", f"{title_name}.txt")
            msg = await ctx.reply("**🎉Here is your crawled novel**", file=file)
            download_url = msg.attachments[0].url
        if download_url:
            novel_data = [
                await bot.mongo.library.next_number,
                title_name,
                "",
                0,
                "chinese (simplified)",
                self.get_tags(title_name),
                download_url,
                size,
                ctx.author.id,
                datetime.datetime.utcnow().timestamp(),
            ]
            data = Novel(*novel_data)
            await bot.mongo.library.add_novel(data)
        os.remove(f"{title}.txt")
        del bot.crawler[ctx.author.id]
