# encoding: UTF-8

"""
市价止损模板
按照能挂出的最大或最小价格平仓
"""

from vnpy.trader.vtConstant import *
# EMPTY_STRING, DIRECTION_LONG, DIRECTION_SHORT,OFFSET_OPEN, OFFSET_CLOSE,
# STATUS_CANCELLED,STATUS_NOTTRADED,STATUS_PARTTRADED,STATUS_ALLTRADED
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)

from collections import defaultdict
import numpy as np
import pandas as pd
import talib as ta
import time
from datetime import datetime


########################################################################
class Test2Strategy(CtaTemplate):
    """配对交易策略"""
    className = 'Test2Strategy'
    author = '市价止损模板'

    # 策略交易标的
    #symbolList = []                 # 初始化为空
    symbol = EMPTY_STRING

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
        super(Test2Strategy, self).__init__(ctaEngine, setting)

  
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)
        # 读取交易品种  
        self.symbol = self.symbolList[0] 
        
        ### 初始化模板需要的变量
        # 无

        
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
        在tick里面保留self.tick
        """
        self.tick = tick
        #### 下面代码可以在onTick，onBar都可以使用
        # stopShort, 平空仓， stopBuy，平多仓
        stopShort, stopBuy = False, False
        if stopShort:
            self.cover(self.symbol,self.tick.upperLimit-0.001,1)
        if stopBuy:
             self.sell(self.symbol,self.tick.lowerLimit+0.001,1)
                 
      
    
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""   
        
        self.putEvent()


    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        # 下单后报单      
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass

