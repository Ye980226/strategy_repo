# encoding: UTF-8

"""
平滑进出场模板说明
在onTick中进行判断，当出现合适价位时进场或出场
可以通过空值sign的值做到对进出场的控制
需要多import一个ctaBase
主要策略逻辑集中在3个地方
onInit， onTick ，onOrder
"""

from vnpy.trader.vtConstant import *
# EMPTY_STRING, DIRECTION_LONG, DIRECTION_SHORT,OFFSET_OPEN, OFFSET_CLOSE,
# STATUS_CANCELLED,STATUS_NOTTRADED,STATUS_PARTTRADED,STATUS_ALLTRADED
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate)
from vnpy.trader.app.ctaStrategy.ctaBase import *

from collections import defaultdict
import numpy as np
import pandas as pd
import talib as ta
import time
from datetime import datetime


########################################################################
class TestStrategy(CtaTemplate):
    """配对交易策略"""
    className = 'TestStrategy'
    author = '平滑进场场模板'

    # 策略交易标的
    #symbolList = []                 # 初始化为空
    symbol = EMPTY_STRING

    # 策略变量
    posSize = 1
    waitCount = 0

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(TestStrategy, self).__init__(ctaEngine, setting)

  
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)
        # 读取交易品种  
        self.symbol = self.symbolList[0] 
        
        ### 初始化模板需要的变量
        self.smoothSign = 'stop'
        self.smoothPrice = 0
        self.smoothVolume = 0 
        self.smoothPerVolume = 0 
        self.smoothTime = None
        self.smoothDict={'orderID':'OKEX_CNM_000','traded':0,'total':0,'type':None}
        #######################
        
        #### 测试用信号发生器 ###
        self.count = 0



        
        self.putEvent()
    
    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)    
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        
        """
        平滑进出场信号
        需要的变量:
        self.smoothSign = CTAORDER_BUY,CTAORDER_SELL,CTAORDER_SHORT,CTAORDER_COVER,stop
        self.smoothVolume: 累计需要成交的量
        self.smoothprice：可接受的最不利价格
        self.smoothPerVolume: 每次下的量

        其中价格和单的类型相对应，比如当sign是buy命令时，price为可接受的最高价
        
        当sign是stop时会触发停止进出场逻辑，此时未成交的单会被撤销，如果已成交不足volume也不会撤单
        
        这套模版用于平滑进出场的价格，避免过大的滑点损失。
        如果遇到必须不计代价成交的情况，比如市价止损出场，请不要使用这套模版
        """
        
        ### 测试用信号发生器 ###
        self.count += 1
        if self.count == 10:
            self.smoothSign = CTAORDER_BUY
            self.smoothVolume = 3
            self.smoothPrice = tick.askPrice3
            self.smoothPerVolume = 1

        
        ### 模版主体逻辑 ####
        self.tick = tick
        if self.smoothSign != 'stop':
            if not self.smoothTime:
                ## 第一次发单
                orderID = self.sendOrder(self.smoothSign,self.symbol,self.smoothPrice,self.smoothPerVolume)[0]
                self.smoothDict={'orderID':orderID,'traded':0,'total':self.smoothVolume,'type':'untraded'}
                self.smoothTime = tick.datetime
            else:
                ## 第二次发单开始要看到时间
                if (tick.datetime - self.smoothTime).total_seconds() > 5 and self.smoothDict['traded'] != self.smoothDict['total']:
                    if self.smoothDict['type'] == 'untraded':  # 上一次发单未全部成交,保险起见先撤销剩余的开仓单
                        self.cancelOrder(self.smoothDict['orderID'])
                    elif self.smoothDict['type'] == 'full':   # 上一次发单已经全部成交，可以直接进入下一次发单逻辑
                        volume = min(self.smoothDict['total']-self.smoothDict['traded'],self.smoothPerVolume)
                        orderID = self.sendOrder(self.smoothSign,self.symbol,self.smoothPrice,volume)[0]
                        self.smoothDict['orderID'] = orderID
                        self.smoothDict['time'] = self.tick.datetime
                        self.smoothTime = self.tick.datetime                                        

        elif self.smoothSign == 'stop':
            if not self.smoothTime: # 表示未完成全部成交
                self.cancelOrder(self.smoothDict['orderID'])           
      
    
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""   
        self.writeCtaLog(u'收到订单状态：%s, :status:%s, traded:%s, total:%s,order.price:%s'%(order.vtOrderID,order.status,order.tradedVolume,order.totalVolume,order.price)) 

        ############## 模版主体逻辑 ################ 
        if order.vtOrderID == self.smoothDict['orderID']:
            ### 对多种状态进行处理
            if order.status == STATUS_PARTTRADED:  #这是一次部分成交
                self.smoothDict['traded'] += order.thisTradedVolume
            elif order.status == STATUS_ALLTRADED: #这是一次全部成交
                self.smoothDict['traded'] += order.thisTradedVolume
                self.smoothDict['type'] = 'full'
                if self.smoothDict['traded'] == self.smoothDict['total']:
                    #### 完成本次成交,返回初始化操作
                    self.smoothSign = 'stop'
                    self.smoothPrice = 0
                    self.smoothVolume = 0 
                    self.smoothPerVolume = 0 
                    self.smoothTime = None
                    self.smoothDict={'orderID':'OKEX_CNM_000','traded':0,'total':0,'type':None}
            elif order.status == STATUS_CANCELLED:
                if self.smoothSign == 'stop':
                    ### 返回初始化操作
                    self.smoothPrice = 0
                    self.smoothVolume = 0 
                    self.smoothPerVolume = 0 
                    self.smoothTime = None
                    self.smoothDict={'orderID':'OKEX_CNM_000','traded':0,'total':0,'type':None}
                else:
                    ## 撤销后再一次发单
                    volume = min(self.smoothDict['total']-self.smoothDict['traded'],self.smoothPerVolume)
                    orderID = self.sendOrder(self.smoothSign,self.symbol,self.smoothPrice,volume)[0]
                    self.smoothDict['orderID'] = orderID
                    self.smoothTime = self.tick.datetime 
        ########################################

        self.putEvent()


    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # 下单后报单  
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass

