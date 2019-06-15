from time import sleep
import os

from vnpy.event import EventEngine2
from vnpy.trader.vtEvent import EVENT_LOG
from vnpy.trader.vtEngine import MainEngine, LogEngine
from vnpy.trader.gateway import okexGateway
from vnpy.trader.app import ctaStrategy
from vnpy.trader.app.ctaStrategy.ctaBase import EVENT_CTA_LOG

def findConnectKey():
    files=os.listdir(".")
    for file in files:
        if file.find("_connect.json")>=0:
            return file.replace("_connect.json","")
#----------------------------------------------------------------------
def runChildProcess():
    """子进程运行函数"""
    print('-'*30)
    # 创建日志引擎
    le = LogEngine()
    le.setLogLevel(le.LEVEL_INFO)
    # le.addConsoleHandler()
    # le.addFileHandler()
    
    le.info(u'启动CTA策略运行子进程')
    
    ee = EventEngine2()
    le.info(u'事件引擎创建成功')
    
    me = MainEngine(ee)
    me.addGateway(okexGateway)
    me.addApp(ctaStrategy)
    le.info(u'主引擎创建成功')
    
    ee.register(EVENT_LOG, le.processLogEvent)
    ee.register(EVENT_CTA_LOG, le.processLogEvent)
    le.info(u'注册日志事件监听')

    KEY = findConnectKey()
    me.connect(KEY)
    le.info(u'连接行情和交易接口')
    
    sleep(6)                        # 等待CTP接口初始化
    me.dataEngine.saveContracts()   # 保存合约信息到文件
    
    cta = me.getApp(ctaStrategy.appName)
    
    cta.loadSetting()
    cta.initAll()    
    cta.startAll()
    
if __name__ == '__main__':
    runChildProcess()