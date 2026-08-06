import time
from typing import Dict, Any


def like_feed(opuin:int,appid: int=311, fid: str=None, cur_key: str=None,uni_key:str=None) -> dict:
    """点赞QQ空间动态参数解析"""
    params = {
        'qzreferrer': f'https://user.qzone.qq.com/{opuin}',  # 来源
        'opuin': opuin,           # 操作者QQ
        'unikey': uni_key,  # 动态唯一标识
        'curkey': cur_key,      # 要操作的动态对象
        'appid': appid,         # 应用ID(说说:311)
        'from': 1,              # 来源
        'typeid': 0,            # 类型ID
        'abstime': int(time.time()),  # 当前时间戳
        'fid': fid,         # 动态ID
        'active': 0,            # 活动ID
        'format': 'json',        # 返回格式
        'fupdate': 1,           # 更新标记
    }
    return params

def get_feeds(uin: int, g_tk: int, page: int = 1, count: int = 10,begintime:int=0) -> Dict[str, Any]:
    """好友动态说说参数解析"""
    params = {
    "uin": uin,              # QQ号
    "scope": 0,              # 访问范围
    "view": 1,              # 查看权限
    "filter": "all",        # 全部动态
    "flag": 1,              # 标记
    "applist": "all",       # 所有应用
    "pagenum": page,        # 页码
    "count": count,         # 每页条数
    "aisortEndTime": 0,     # AI排序结束时间
    "aisortOffset": 0,      # AI排序偏移
    "aisortBeginTime": 0,   # AI排序开始时间
    "begintime": begintime,         # 开始时间
    "format": "json",       # 返回格式
    "g_tk": g_tk,          # 令牌
    "useutf8": 1,          # 使用UTF8编码
    "outputhtmlfeed": 1    # 输出HTML格式
    }
    return params

def get_self_zone(target_qq: int, g_tk: int,  pos: int = 0, num: int = 20) -> Dict[str, Any]:
    """获取指定QQ的说说数据"""
    params = {
        "uin": target_qq,          # 目标QQ
        "ftype": 0,               # 全部说说
        "sort": 0,                # 最新在前
        "pos": pos,               # 起始位置
        "num": num,               # 获取条数
        "replynum": 100,          # 评论数
        "g_tk": g_tk,            # 访问令牌
        "callback": "_preloadCallback",
        "code_version": 1,
        "format": "jsonp",
        "need_private_comment": 1
    }
    return params


def get_album_list(
    target_qq: int,
    login_qq: int,
    g_tk: int,
    start: int = 0,
    count: int = 30,
) -> Dict[str, Any]:
    """获取指定空间的相册列表参数。"""
    return {
        "g_tk": g_tk,
        "hostUin": target_qq,
        "uin": login_qq,
        "appid": 4,
        "inCharset": "utf-8",
        "outCharset": "utf-8",
        "source": "qzone",
        "plat": "qzone",
        "format": "jsonp",
        "notice": 0,
        "filter": 1,
        "handset": 4,
        "pageNumModeSort": 40,
        "pageNumModeClass": 15,
        "mode": 2,
        "pageStart": start,
        "pageNum": count,
        "needUserInfo": 1,
        "idcNum": 4,
        "callback": "shine_Callback",
        "callbackFun": "shine",
    }


def get_album_photos(
    target_qq: int,
    login_qq: int,
    album_id: str,
    g_tk: int,
    start: int = 0,
    count: int = 100,
) -> Dict[str, Any]:
    """获取指定相册照片列表参数。"""
    return {
        "g_tk": g_tk,
        "mode": 0,
        "idcNum": 4,
        "hostUin": target_qq,
        "topicId": album_id,
        "noTopic": 0,
        "uin": login_qq,
        "pageStart": start,
        "pageNum": count,
        "skipCmtCount": 0,
        "singleurl": 1,
        "batchId": "",
        "notice": 0,
        "appid": 4,
        "inCharset": "utf-8",
        "outCharset": "utf-8",
        "source": "qzone",
        "plat": "qzone",
        "outstyle": "json",
        "format": "jsonp",
        "json_esc": 1,
        "question": "",
        "answer": "",
        "callback": "shine_Callback",
        "callbackFun": "shine",
    }


def get_video_info(
    target_qq: int,
    login_qq: int,
    album_id: str,
    sloc: str,
    g_tk: int,
) -> Dict[str, Any]:
    """获取相册视频或实况图的真实媒体地址参数。"""
    return {
        "g_tk": g_tk,
        "callback": "viewer_Callback",
        "topicId": album_id,
        "picKey": sloc,
        "cmtOrder": 1,
        "fupdate": 1,
        "plat": "qzone",
        "source": "qzone",
        "cmtNum": 0,
        "inCharset": "utf-8",
        "outCharset": "utf-8",
        "callbackFun": "viewer",
        "uin": login_qq,
        "hostUin": target_qq,
        "appid": 4,
        "isFirst": 1,
    }

def get_send_zone(target_qq:int,content:str) -> Dict[str, Any]:
    """发送说说参数解析"""
    parms = {
        "syn_tweet_verson": 1,  # 说说版本
        "paramstr": 1,  # 参数
        "pic_template": "",  # 图片模板
        "richtype": "",  # 富文本类型
        "richval": "",  # 富文本值
        "hostuin": target_qq,  # 操作QQ
        "who": 1,  # 说说类型
        "con": content,  # 说说内容
        "feedversion": 1,  # 说说版本
        "ver": 1,  # 版本
        "ugc_right": 1,  # 权限
        "to_sign": 0,  # 签名
        "code_version": 1,
        "format": "fs",
        "qzreferrer": f"https://user.qzone.qq.com/{target_qq}"
    }
    return parms


def get_send_comment(opuin: int,uin:int, content: str, fid: str) -> Dict[str, Any]:
    """发送说说评论参数解析"""
    parms = {
        "uin": uin,  # 目标QQ
        "hostUin": opuin,  # 操作QQ
        "feedsType": 100,  # 说说类型
        "inCharset": "utf-8",  # 字符集
        "outCharset": "utf-8",  # 字符集
        "topicId": fid,  # 说说ID
        "plat": "qzone",  # 平台
        "source": "ic",  # 来源
        "platformid": 50,  # 平台id
        "format": "fs",  # 返回格式
        "ref": "feeds",  # 引用
        "content": content,  # 评论内容
    }
    return parms

def get_del_zone(uin: int, fid: str,curkey:str,timestamp:int) -> Dict[str, Any]:
    """删除说说参数解析"""
    parms = {
        "uin": uin,  # 目标QQ
        "topicId": fid,  # 说说ID
        "feedsType": 0,  # 说说类型
        "feedsFlag": 0,  # 说说标记
        "feedsKey": curkey,  # 当前key
        "feedsAppid": 311,
        "feedsTime": timestamp,  # 时间戳
        "fupdate": 1,  # 更新标记
        "ref": "feeds",
        "qzreferrer": f"https://user.qzone.qq.com/{uin}",
    }
    return parms

def get_forward_zone(uin: int,opuin:int, tid: str,connent:str) -> Dict[str, Any]:
    """转发说说参数解析"""
    parms = {
        "t1_uin": uin,  # 目标QQ
        "t1_source": 1,  # 来源
        "tid": tid,  # 说说ID
        "signin": 0,  # 签名
        "con": connent,  # 内容
        "with_cmt": 0,  # 评论
        "fwdToWeibo": 0,  # 转发到微博
        "forward_source": 2,  # 转发来源
        "code_version": 1,  # 版本
        "format": "fs",  # 返回格式
        "hostuin": opuin,  # 操作QQ
        "qzreferrer": f"https://user.qzone.qq.com/{uin}"
    }
    return parms
