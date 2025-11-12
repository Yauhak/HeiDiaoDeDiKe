import re
import os
import json
import requests
from bs4 import BeautifulSoup
from moviepy import *

#这是一种非常非常经典的浏览器请求头
#用于模拟浏览器环境
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Encoding': 'identity', 
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Referer': 'https://www.bilibili.com/',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'video',
    'Sec-Fetch-Mode': 'no-cors',
    'Sec-Fetch-Site': 'cross-site'
}
#与比利比利服务器的会话句柄
session=None

#模拟正常人类通过浏览器浏览B站的过程
#首先访问一次B站首页
#在此过程中获取的某些cookies可能在后续过程有用
#无论如何，做个初始化是保险的
def init_catcher():
    global session
    session = requests.Session()
    session.headers.update(headers)
    req=session.get('https://www.bilibili.com/')
    if req.status_code==200:
        print("初始化成功\n")
        return 1
    else:
        return 0

#比利比利的搜索链接
#https://search.bilibili.com/all?keyword=XXX&search_source=1
#如果page > 1则在网址后添加[&page=XXX][&o=(XXX-1)*30]
#即表示翻到第几页
def search_with_params(keyword,page=1):
    url = 'https://search.bilibili.com/all'
    params = {
        'keyword': f'{keyword}',
        'search_source': '1'
    }
    if page > 1:
        params['page']=f'{page}'
        params['o']=f'{30*(int(page)-1)}'
    elif page < 1:
        return [-1,'']
    response = session.get(url, params=params)
    if response.status_code==200:
        print("搜索成功\n")
        #print(response.text)
        return [1,response.text]
    else:
        print("错误码{response.status_code}\n")
        return [0,'']

#通过search_with_params得到的网页内容关于视频地址与名字的部分结构如下：
#<a href="AAA"...>，此处的AAA代表视频播放地址
#...
#<img ... alt="BBB">，此处的BBB既描述了加载的图片资源的名字，也是该视频的名字
#...
#<a href="AAA"...>，后面又会重复出现一次该视频的播放地址
#那么在基于a href和img alt标签进行查找的过程中，视频网址会被统计两次
#因此在构建视频名字和网址的映射时要排除重复部分
def get_video_play_list(html_text):
    soup=BeautifulSoup(html_text,"html.parser")
    video_list=[]
    video_title=[]
    mapping=[]
    for a in soup.find_all('a',href=True):
        if not "space" in a['href']:
            video_list.append(a['href'])
    for img in soup.find_all('img',alt=True):
        if len(img['alt'])>0:
            video_title.append(img['alt'])
    for i in range(0,len(video_title)):
        mapping.append([video_title[i],video_list[i*2]])
    return mapping

#从视频播放链接中解析出视频和音频文件的源地址
def parse_bilibili_video_urls(html_content):
    #基于对扒下来的网页源码的分析
    #视频和音频文件的地址被记录在window.__playinfo__这个“关键字”之后
    #因此我们需要对这部分进行解析
    playinfo_pattern = r'window\.__playinfo__\s*=\s*({.*?})\s*</script>'
    playinfo_match = re.search(playinfo_pattern, html_content, re.DOTALL)
    result = {
        'video_urls': [],
        'video_backup_urls': [],
        'audio_urls': [],
        'audio_backup_urls': []
    }
    if playinfo_match:
        try:
            playinfo_json = playinfo_match.group(1)
            playinfo_data = json.loads(playinfo_json)
            #print(playinfo_data)
            if 'data' in playinfo_data and 'dash' in playinfo_data['data']:
                dash_data = playinfo_data['data']['dash']
                if 'video' in dash_data:
                    for video in dash_data['video']:
                        if 'baseUrl' in video:
                            result['video_urls'].append({
                                'id': video.get('id'),
                                'quality': video.get('id'),
                                'width': video.get('width'),
                                'height': video.get('height'),
                                'bandwidth': video.get('bandwidth'),
                                'codecs': video.get('codecs'),
                                'url': video['baseUrl']
                            })
                        if 'backupUrl' in video:
                            result['video_backup_urls'].append({
                                'id': video.get('id'),
                                'quality': video.get('id'),
                                'width': video.get('width'),
                                'height': video.get('height'),
                                'bandwidth': video.get('bandwidth'),
                                'codecs': video.get('codecs'),
                                'url': video['backupUrl']
                            })
                if 'audio' in dash_data:
                    for audio in dash_data['audio']:
                        if 'baseUrl' in audio:
                            result['audio_urls'].append({
                                'id': audio.get('id'),
                                'bandwidth': audio.get('bandwidth'),
                                'codecs': audio.get('codecs'),
                                'url': audio['baseUrl']
                            })
                        if 'backupUrl' in audio:
                            result['audio_backup_urls'].append({
                                'id': audio.get('id'),
                                'bandwidth': audio.get('bandwidth'),
                                'codecs': audio.get('codecs'),
                                'url': audio['backupUrl']
                            })
                            
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
    #print(result)
    return result

def get_video_and_audio(play_address,video_name):
    webpage=session.get(play_address)
    if webpage.status_code==200:
        #print(webpage.text)
        final_addresses=parse_bilibili_video_urls(webpage.text)
        #print(final_addresses)
        illegal_chars = r'[<>:"/\\|?*\x00-\x1f]'
        safe_name = re.sub(illegal_chars, '', video_name)
        video_m4s_addr=None
        audio_m4s_addr=None
        #此处的处理就涉及到对CDN的考量
        #xy118x184x254x108xy.mcdn.bilivideo.cn这种MCDN就通常可直连下载
        #带upos-sz-前缀的貌似是B站核心CDN，一般难以访问（返回403）
        #因此我们优先选择MCDN
        for v in range(len(final_addresses['video_urls'])):
            if "mcdn" in final_addresses['video_urls'][v]['url']:
                video_m4s_addr=final_addresses['video_urls'][v]['url']
                break
        if video_m4s_addr==None:
            for v in range(len(final_addresses['video_backup_urls'])):
                if "mcdn" in final_addresses['video_backup_urls'][v]['url']:
                    video_m4s_addr=final_addresses['video_backup_urls'][v]['url']
                    break
        #从备用网址中查看是否有MCDN
        for a in range(len(final_addresses['audio_urls'])):
            if "mcdn" in final_addresses['audio_urls'][a]['url']:
                audio_m4s_addr=final_addresses['audio_urls'][a]['url']
                break
        if video_m4s_addr==None:
            for a in range(len(final_addresses['audio_backup_urls'])):
                if "mcdn" in final_addresses['audio_backup_urls'][a]['url']:
                    video_m4s_addr=final_addresses['audio_backup_urls'][a]['url']
                    break
        #-----------------------------------------------------------
        #别无可选就选择默认链接（final_addresses中第一个链接）
        #虽然一般铁定返回403
        #当然，也可以选择不跟这个视频较劲，去看其他视频哦~（开玩笑）
        #另外这些链接也是在不断变化的
        #也有可能多刷几次就能刷出MCDN的副本了
        #-----------------------------------------------------------
        #现在没事了
        #之前在get媒体流文件那里出了点小Bug
        #丢失了会话上下文
        #导致下载带upos-sz-前缀的链接下的文件失败
        if video_m4s_addr==None:
            video_m4s_addr=final_addresses['video_urls'][0]['url']
        if audio_m4s_addr==None:
            audio_m4s_addr=final_addresses['audio_urls'][0]['url']
        video_temp = f"C:\\Users\\Administrator\\Desktop\\{safe_name}_video.m4s"
        audio_temp = f"C:\\Users\\Administrator\\Desktop\\{safe_name}_audio.m4s"
        print(f"正在下载视频流...来源：{video_m4s_addr}\n")
        video_response = session.get(video_m4s_addr, stream=True)
        with open(video_temp, 'wb') as f:
            for chunk in video_response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"正在下载音频流...来源：{audio_m4s_addr}\n")
        audio_response = session.get(audio_m4s_addr, stream=True)
        with open(audio_temp, 'wb') as f:
            for chunk in audio_response.iter_content(chunk_size=8192):
                f.write(chunk)
        #将音频和视频合并为一个文件
        video_clip = VideoFileClip(video_temp)
        audio_clip = AudioFileClip(audio_temp)
        video_with_audio = video_clip.with_audio(audio_clip)
        video_with_audio.write_videofile(
            f"C:\\Users\\Administrator\\Desktop\\{safe_name}.mp4",
            codec='libx264',  # 视频编码
            audio_codec='aac',  # 音频编码
            temp_audiofile='temp-audio.m4a',  # 临时音频文件
            remove_temp=True  # 完成后删除临时文件
        )
        video_clip.close()
        audio_clip.close()
        video_with_audio.close()
        #删除中间文件
        os.remove(video_temp)
        os.remove(audio_temp)
        return 1
    else:
        return 0

#这部分只是演示demo哦
#只选择了搜索结果中的第一个视频进行解析下载
#反正该有的功能都有的~
if __name__ == '__main__':
    init_catcher()
    search_result=search_with_params('冬之花')
    if search_result[0]==1:
        map=get_video_play_list(search_result[1])
        #print(map[0][0],map[0][1])
        get_video_and_audio(f'https:{map[0][1]}',map[0][0])
        input("已完成")
