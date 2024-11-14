import base64
import httpx
import nonebot
from datetime import datetime

from nonebot.log import logger
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.rule import to_me
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import (
    Message,
    MessageSegment,
    PrivateMessageEvent,
    MessageEvent,
    helpers,
)
from nonebot.plugin import PluginMetadata
from .config import Config, ConfigError
from openai import AsyncOpenAI

__plugin_meta__ = PluginMetadata(
    name="OneAPI和OpenAI聊天Bot",
    description="具有上下文关联和多模态识别，适配OneAPI和OpenAI官方的nonebot插件。",
    usage="""
    @机器人发送问题时机器人不具有上下文回复的能力
    chat 使用该命令进行问答时，机器人具有上下文回复的能力
    lear 清除当前用户的聊天记录
    """,
    config=Config,
    extra={},
    type="application",
    homepage="https://github.com/Alpaca4610/nonebot_plugin_chatgpt_turbo",
    supported_adapters={"~onebot.v11"},
)


plugin_config = Config.parse_obj(nonebot.get_driver().config.dict())


if not plugin_config.oneapi_key:
    raise ConfigError("请配置大模型使用的KEY")
if plugin_config.oneapi_url:
    client = AsyncOpenAI(
        api_key=plugin_config.oneapi_key, base_url=plugin_config.oneapi_url
    )
else:
    client = AsyncOpenAI(api_key=plugin_config.oneapi_key)

model_id = plugin_config.oneapi_model

# public = plugin_config.chatgpt_turbo_public
session = {}

# 带上下文的聊天
chat_record = on_command("mchat",aliases={"mct"}, block=False, priority=1)

# 不带上下文的聊天
# chat_request = on_command("chat",aliases={"ct"}, block=False, priority=99)
chat_request = on_command("",rule=to_me(), block=False, priority=99)

# 清除历史记录
clear_request = on_command("clear", block=True, priority=1)

# 切换全局人格
swc_global_person = on_command("swcp",block=True,permission=SUPERUSER)

# 清除全局上下文聊天
clear_all_request = on_command("clear_all", block=True, priority=1, permission=SUPERUSER)

# spModel
spModel = on_command("spchat",aliases={"spct"},permission=SUPERUSER)
spModel_Mem = on_command("spmchat",aliases={"spmct"},permission=SUPERUSER)

# checkApiKeyUsedTimes
checkapiKeyUse = on_command("apiuse")


from .prompt import person_word_list

# 默认人格配置项
select_person = person_word_list["catgril"]

# 需要权限的模型
spModel_usedModel = "gpt-4o-mini"


@swc_global_person.handle()
async def _(event: MessageEvent, msg: Message = CommandArg()):
    global select_person
    
    select_person = person_word_list[msg.extract_plain_text()]
    await swc_global_person.finish("已切换全局人格！")

@clear_all_request.handle()
async def _(event: MessageEvent):
    global session
    session = {}
    await clear_all_request.finish("成功清除所有会话记录！")


# 带记忆的聊天
@chat_record.handle()
async def _(event: MessageEvent, msg: Message = CommandArg()):
    # 若未开启私聊模式则检测到私聊就结束
    if isinstance(event, PrivateMessageEvent) and not plugin_config.enable_private_chat:
        # chat_record.finish("对不起，私聊暂不支持此功能。")
        chat_record.finish()
    content = msg.extract_plain_text()
    img_url = helpers.extract_image_urls(event.message)
    if content == "" or content is None:
        await chat_request.finish()
        await chat_request.finish(MessageSegment.text("内容不能为空！"), at_sender=True)
        
    if not check_apiKey_usedTimes():
        await chat_record.finish("API KEY使用次数已达上限！", at_sender=True)
        
    
    await chat_request.send(
        MessageSegment.text("思考中......")
    )
    
    session_id = event.get_session_id()
    if session_id not in session:
        session[session_id] = []
        session[session_id].append(
            {
                "role": "system",
                "content": select_person
            }
            )

    if not img_url:
        try:
            session[session_id].append({"role": "user", "content": content})
            response = await client.chat.completions.create(
                model=model_id,
                messages=session[session_id],
            )
        except Exception as error:
            await chat_record.finish(str(error), at_sender=True)
        await chat_record.finish(
            MessageSegment.text(str(response.choices[0].message.content)),
            at_sender=True,
        )
    else:
        try:
            image_data = base64.b64encode(httpx.get(img_url[0]).content).decode("utf-8")
            session[session_id].append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_data}"},
                        },
                    ],
                }
            )
            response = await client.chat.completions.create(
                model=model_id, messages=session[session_id]
            )
        except Exception as error:
            await chat_record.finish(str(error), at_sender=True)
        await chat_record.finish(
            MessageSegment.text(response.choices[0].message.content), at_sender=True
        )


# 不带记忆的对话
@chat_request.handle()
async def _(event: MessageEvent, msg: Message = CommandArg()):
    if isinstance(event, PrivateMessageEvent) and not plugin_config.enable_private_chat:
        
        await chat_record.finish()

    img_url = helpers.extract_image_urls(event.message)
    content = msg.extract_plain_text()
    if content == "" or content is None:
        await chat_request.finish()
        await chat_request.finish(MessageSegment.text("内容不能为空！"), at_sender=True)
    
    
    if not check_apiKey_usedTimes():
        await chat_request.finish("API KEY使用次数已达上限！", at_sender=True)
    
    await chat_request.send(
        MessageSegment.text("思考中......")
    )
    
    if not img_url:
        try:
            
            response = await client.chat.completions.create(
                model=model_id,
                messages=[
                    {
                    "role": "system",
                    "content": select_person
                    },
                    {"role": "user", "content": content}
                    ],
            )
        except Exception as error:
            await chat_request.finish(str(error), at_sender=True)
        await chat_request.finish(
            MessageSegment.text(str(response.choices[0].message.content)),
            at_sender=True,
        )
    else:
        try:
            image_data = base64.b64encode(httpx.get(img_url[0]).content).decode("utf-8")
            response = await client.chat.completions.create(
                model=model_id,
                messages=[
                    
                    {
                    "role": "system",
                    "content": select_person
                    },
                    
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": content},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_data}"
                                },
                            },
                        ],
                    }
                ],
            )
        except Exception as error:
            await chat_request.finish(str(error), at_sender=True)
        await chat_request.finish(
            MessageSegment.text(response.choices[0].message.content), at_sender=True
        )

@spModel_Mem.handle()
async def _(event: MessageEvent, msg: Message = CommandArg()):
    content = msg.extract_plain_text()
    img_url = helpers.extract_image_urls(event.message)
    if content == "" or content is None:
        await spModel_Mem.finish()
        
        
    if not check_apiKey_usedTimes():
        await spModel_Mem.finish("API KEY使用次数已达上限！", at_sender=True)
        
    
    await spModel_Mem.send(
        MessageSegment.text("思考中......")
    )
    
    session_id = event.get_session_id()
    if session_id not in session:
        session[session_id] = []
        session[session_id].append(
            {
                "role": "system",
                "content": select_person
            }
            )

    if not img_url:
        try:
            session[session_id].append({"role": "user", "content": content})
            response = await client.chat.completions.create(
                model=spModel_usedModel,
                messages=session[session_id],
            )
        except Exception as error:
            await spModel_Mem.finish(str(error), at_sender=True)
        await spModel_Mem.finish(
            MessageSegment.text(str(response.choices[0].message.content)),
            at_sender=True,
        )
    else:
        try:
            image_data = base64.b64encode(httpx.get(img_url[0]).content).decode("utf-8")
            session[session_id].append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": content},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_data}"},
                        },
                    ],
                }
            )
            response = await client.chat.completions.create(
                model=spModel_usedModel, messages=session[session_id]
            )
        except Exception as error:
            await spModel_Mem.finish(str(error), at_sender=True)
        await spModel_Mem.finish(
            MessageSegment.text(response.choices[0].message.content), at_sender=True
        )


@spModel.handle()
async def _(event: MessageEvent, msg: Message = CommandArg()):
    # if isinstance(event, PrivateMessageEvent) and not plugin_config.enable_private_chat:
        
    #     await spModel.finish()




    img_url = helpers.extract_image_urls(event.message)
    content = msg.extract_plain_text()
    if content == "" or content is None:
        await spModel.finish(MessageSegment.text("内容不能为空！"), at_sender=True)
    
    
    if not check_apiKey_usedTimes():
        await spModel.finish("API KEY使用次数已达上限！", at_sender=True)
    
    await spModel.send(
        MessageSegment.text("思考中......")
    )
    
    if not img_url:
        try:
            
            response = await client.chat.completions.create(
                model=spModel_usedModel,
                messages=[
                    {
                    "role": "system",
                    "content": select_person
                    },
                    {"role": "user", "content": content}
                    ],
            )
        except Exception as error:
            await spModel.finish(str(error), at_sender=True)
        await spModel.finish(
            MessageSegment.text(str(response.choices[0].message.content)),
            at_sender=True,
        )
    else:
        try:
            image_data = base64.b64encode(httpx.get(img_url[0]).content).decode("utf-8")
            response = await client.chat.completions.create(
                model=spModel_usedModel,
                messages=[
                    
                    {
                    "role": "system",
                    "content": select_person
                    },
                    
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": content},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_data}"
                                },
                            },
                        ],
                    }
                ],
            )
        except Exception as error:
            await spModel.finish(str(error), at_sender=True)
        await spModel.finish(
            MessageSegment.text(response.choices[0].message.content), at_sender=True
        )



@clear_request.handle()
async def _(event: MessageEvent):
    del session[event.get_session_id()]
    await clear_request.finish(
        MessageSegment.text("成功清除历史记录！"), at_sender=True
    )


@checkapiKeyUse.handle()
async def _():
    msg = f"当前Api使用次数:{onlyGetApiUsedTimes()}/180"
    await checkapiKeyUse.finish(msg)

def check_apiKey_usedTimes() -> bool:
    '''
    检查apiKey使用次数 防止被封禁\n
    返回是/否可以继续使用
    '''
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(f"apiKey_usedTimes_{today}.txt","r") as f:
            token_usedTimes = int(f.read())
            
            if token_usedTimes >= 180:
                return False
            else:
                token_usedTimes += 1
                with open(f"apiKey_usedTimes_{today}.txt","w") as f:
                    f.write(str(token_usedTimes))
                return True
    except FileNotFoundError:
        with open(f"apiKey_usedTimes_{today}.txt","w") as f:
            f.write("1")
            return True
    
    pass

def onlyGetApiUsedTimes():
    
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(f"apiKey_usedTimes_{today}.txt","r") as f:
            token_usedTimes = int(f.read())
            return token_usedTimes
    except FileNotFoundError:
        return 0
    pass

# # 根据消息类型创建会话id
# def create_session_id(event):
#     if isinstance(event, PrivateMessageEvent):
#         session_id = f"Private_{event.user_id}"
#     elif public:
#         session_id = event.get_session_id().replace(f"{event.user_id}", "Public")
#     else:
#         session_id = event.get_session_id()
#     return session_id
