import asyncio

from typing import List

from graia.application import GraiaMiraiApplication, Session
from graia.application.entities import UploadMethods
from graia.application.event.messages import GroupMessage, FriendMessage, TempMessage
from graia.application.event.mirai import NewFriendRequestEvent
from graia.application.friend import Friend
from graia.application.group import Group, Member
from graia.application.message.chain import MessageChain
from graia.application.message.elements.internal import Source, Plain, At, Image, Face
from graia.broadcast import Broadcast

from commands import std, easter_eggs
from config import host, auth_key, account, database_path, information_groups
from icu.decorator import command
from icu.database import Database


loop = asyncio.get_event_loop()
bcc = Broadcast(loop=loop)
app = GraiaMiraiApplication(
    broadcast=bcc, connect_info=Session(
        host=host, authKey=auth_key, account=account, websocket=True
    )
)

database = Database(database_path)
command.register(
    registers=(
        std.register_common_commands, std.register_database_commands,
        easter_eggs.register_common_commands,
    ), database=database,
)
aml = [0, 0, 0]  # average_message_length，用于判断大喘气：member_id, length, count


def process(content: str, fuzzy: int = 0) -> list:
    def handle_type(result: dict) -> List:
        if result['type'] == 'text':
            return [Plain(result['return'])]
        elif result['type'] == 'image':
            return [Image.fromLocalFile(result['return'], method=UploadMethods.Temp)]
        elif result['type'] == 'error':
            return [Face(faceId=168), Plain(result['return'])]
        else:
            return []
    # 命令运行
    if content.startswith('/'):
        return handle_type(command.from_str(content[1:]))
    # 关键词回复 + 模糊查询回复
    returns = []
    for result in database.keyword_match(content):
        returns += handle_type(result) + [Plain('\n\n')]
    if fuzzy:
        for result in database.keyword_match(content, fuzzy=fuzzy):
            returns += handle_type(result) + [Plain('\n\n')]
    return returns[:-1]

@bcc.receiver(FriendMessage)  # 好友聊天
async def friend_message_listener(
    app: GraiaMiraiApplication, friend: Friend, message: MessageChain
):
    content = message.asDisplay().strip()
    return_ = process(content, fuzzy=3)
    if return_:
        await app.sendFriendMessage(friend, MessageChain.create(return_))

@bcc.receiver(GroupMessage)  # 群组聊天
async def group_message_listener(
    app: GraiaMiraiApplication, group: Group, member: Member, message: MessageChain
):
    content = message.asDisplay().strip()
    if group.id in information_groups:  # 信息群
        # 特征记录：大喘气
        global aml
        if member.id == aml[0]:
            aml = [member.id, 0, 0]
        aml[1] += len(content)
        aml[2] += 1
        # 判断信息群是否存在低效情况
        tips = ''
        if all(isinstance(element, (Source, Face)) for element in message):
            tips = '【自动回复】信息群请不要单发表情哟~（如有误判请忽略）'
        elif len(set(content)) == 1:  # 避免 '???' '。。。' 等
            tips = '【自动回复】信息群请不要重复单字哟~（如有误判请忽略）'
        elif aml[2]==3 and aml[1]/aml[2]<10:
            tips = '【自动回复】信息群请避免大喘气，否则容易刷丢重要信息（如有误判请忽略）'
        if tips:
            await app.sendTempMessage(
                group, member, MessageChain.create([Plain(tips)]),
                quote=message.get(Source)[0],
            )
        else:
            return
    return_ = process(content)
    if return_:
        # 可能由于风控原因，偶尔无法在群里发言，因此改为私聊回复
        # await app.sendGroupMessage(
        #     group, MessageChain.create(return_), quote=message.get(Source)[0]
        # )
        await app.sendTempMessage(
            group, member, MessageChain.create(return_), quote=message.get(Source)[0]
        )

@bcc.receiver(TempMessage)  # 临时聊天
async def temp_message_listener(
    app: GraiaMiraiApplication, group: Group, member: Member, message: MessageChain
):
    return_ = process(message, fuzzy=3)
    if return_:
        await app.sendTempMessage(group, member, MessageChain.create(return_))

# 同意好友申请后，因为好友身份识别为陌生人导致私戳信息无效，因此不自动同意好友申请
# @bcc.receiver(NewFriendRequestEvent)  # 好友申请
# async def new_friend_request_listener(
#     app: GraiaMiraiApplication, event: NewFriendRequestEvent
# ):
#     await event.accept()


if __name__ == '__main__':
    app.launch_blocking()
