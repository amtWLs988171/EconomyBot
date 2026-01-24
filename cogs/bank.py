import discord
from discord.ext import commands
import random
import time

class BankCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_work = {}  # user_id: timestamp
        self.last_daily = {} # user_id: timestamp

    @commands.command(name="balance", aliases=["money", "bal"])
    async def balance(self, ctx, member: discord.Member = None):
        """自分または他のユーザーの残高を確認します。"""
        if member is None:
            member = ctx.author
        
        bal = await self.bot.bank.get_balance(member)
        
        embed = discord.Embed(color=discord.Color.green())
        embed.set_author(name=f"{member.display_name}", icon_url=member.display_avatar.url)
        embed.add_field(name="残高", value=f"{bal:,} 円")
        
        await ctx.send(embed=embed)

    @commands.command(name="transfer", aliases=["pay"])
    async def transfer(self, ctx, receiver: discord.Member, amount: int):
        """他のユーザーにお金を送ります。"""
        try:
            await self.bot.bank.transfer_credits(ctx.author, receiver, amount)
            embed = discord.Embed(title="送金完了", color=discord.Color.blue())
            embed.description = f"**{ctx.author.display_name}** から **{receiver.display_name}** へ\n`{amount:,} 円`を送金しました。"
            await ctx.send(embed=embed)
        except ValueError as e:
            await ctx.send(f"❌ {str(e)}")
        except Exception as e:
            await ctx.send(f"❌ エラー: {e}")

    @commands.command(name="deposit")
    @commands.has_permissions(administrator=True)
    async def deposit(self, ctx, member: discord.Member, amount: int):
        """(管理者) お金の支給"""
        try:
            await self.bot.bank.deposit_credits(member, amount)
            await ctx.send(f"✅ 支給完了: {member.display_name} (`+{amount:,}`) "
                           f"→ 現在の残高: `{await self.bot.bank.get_balance(member):,} 円`")
        except ValueError as e:
            await ctx.send(f"❌ {str(e)}")


    @commands.command(name="daily")
    async def daily(self, ctx):
        """1日1回、出席ボーナスを受け取ります。"""
        user_id = ctx.author.id
        now = time.time()
        
        # 簡易的な1日チェック (24時間)
        if user_id in self.last_daily:
            diff = now - self.last_daily[user_id]
            if diff < 86400:
                hours = int((86400 - diff) // 3600)
                await ctx.send(f"📅 すでに出席済みです。(残り {hours}時間)")
                return

        amount = 5000
        await self.bot.bank.deposit_credits(ctx.author, amount)
        self.last_daily[user_id] = now
        
        await ctx.send(f"📅 ログボ受取完了: `{amount:,} 円`")

async def setup(bot):
    await bot.add_cog(BankCog(bot))
