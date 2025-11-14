import os
import asyncio
from qzone_api import QzoneApi
from qzone_api.login import QzoneLogin
import demjson3

SESSION_FILE = "qzone_session.json"  # 用来保存登录信息的本地文件


async def login_with_cache():
    """
    优先使用本地缓存的 cookies；
    如果不存在或已失效，则重新扫码登录。
    """
    # 1. 先尝试读取本地 session
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = demjson3.decode(f.read())

            cookies = data["cookies"]
            skey = data["skey"]
            bkn = data["bkn"]
            qq_raw = str(data["qq"])
            # 兼容形如 'o123456' / 'u123456'
            qq = int(qq_raw.lstrip("ou"))

            cookies_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            qzone = QzoneApi()

            # 2. 用缓存 cookies 调一次简单接口测试是否有效
            print("正在尝试使用本地缓存 cookies 登录...")
            test_result = await qzone.get_messages_list(
                target_qq=qq,
                g_tk=bkn,
                cookies=cookies_str,
            )

            # 这里的判断可以根据你真实返回结构再细调
            if test_result:
                print("本地 cookies 可用，免扫码登录成功！")
                return {
                    "code": 0,
                    "qq": qq_raw,
                    "cookies": cookies,
                    "skey": skey,
                    "bkn": bkn,
                }
            else:
                print("本地 cookies 看起来已失效，将重新扫码登录...")

        except Exception as e:
            print(f"读取/使用本地 cookies 失败，将重新扫码登录：{e}")

    # 3. 如果没有缓存或缓存失效，走扫码登录
    qzone_login = QzoneLogin()
    login_result = await qzone_login.login()

    if login_result["code"] == 0:
        print(f"扫码登录成功! QQ: {login_result['qq']}")
        # 把本次登录结果写入本地，方便下次复用
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                f.write(
                    demjson3.encode(
                        {
                            "qq": login_result["qq"],
                            "cookies": login_result["cookies"],
                            "skey": login_result["skey"],
                            "bkn": login_result["bkn"],
                        }
                    )
                )
            print("已将登录信息保存到本地，下次优先使用缓存 cookies。")
        except Exception as e:
            print(f"保存本地 session 文件失败：{e}")

    return login_result


async def main():
    # 先尝试使用缓存登录
    login_result = await login_with_cache()

    if login_result["code"] == 0:
        print(f"登录成功! QQ: {login_result['qq']}")

        cookies = login_result["cookies"]
        cookies_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        skey = login_result["skey"]
        bkn = login_result["bkn"]

        qzone = QzoneApi()

        # 如果 login_result["qq"] 有前缀 o/u，这里再处理一次
        qq_raw = str(login_result["qq"])
        qq = int(qq_raw.lstrip("ou"))

        messages = await qzone._get_zone_list(
            target_qq=qq,
            g_tk=bkn,
            cookies=cookies_str,
        )
        print(messages)

        if isinstance(messages, dict) and "data" in messages:
            for k in messages["data"]:
                await qzone._zanzone(
                    target_qq=qq,
                    g_tk=bkn,
                    cookies=cookies_str,
                    cur_key=k["cur_key"],
                    fid=k["key"],
                    uni_key=k["cur_key"],
                )
            print(f"成功点赞 {len(messages['data'])} 条说说")
        else:
            try:
                for k in messages:
                    await qzone._zanzone(
                        target_qq=qq,
                        g_tk=bkn,
                        cookies=cookies_str,
                        cur_key=k["cur_key"],
                        fid=k["key"],
                        uni_key=k["cur_key"],
                    )
                print(f"成功点赞 {len(messages)} 条说说")
            except Exception as e:
                print("处理说说列表时出错，可打印 messages 看下结构：", e)


if __name__ == "__main__":
    asyncio.run(main())
