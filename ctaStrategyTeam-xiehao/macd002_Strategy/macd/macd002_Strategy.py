# coding: utf-8
from __future__ import division
from vnpy.trader.vtConstant import *

from vnpy.trader.app.ctaStrategy import CtaTemplate

from collections import defaultdict
import numpy as np
import talib as ta
import pandas as pd
from datetime import datetime


class macd002_Strategy(CtaTemplate):
    className = 'macd002_Strategy'
    author = 'Sky'
    # 策略交易标的
    symbol = EMPTY_STRING
    posDict = {}  # 仓位数据缓存
    eveningDict = {}  # 可平仓量数据缓存
    bondDict = {}  # 保证金数据缓存

    # 策略参数
    Window1 = 33
    Window2 = 12
    trailingPercent = 0.002
    fixsize = 2
    stopRatio = 0.01  # 止损百分比
    profitMultiplier1 = 4  # 止盈与止损比例
    profitMultiplier2 = 2
    mean = EMPTY_FLOAT
    transactionPrice = {}  # 记录成交价格
    intraTradeHighDict = {}
    intraTradeLowDict = {}
    trend = {}  # 均线趋势，多头1，空头-1
    cross = {}
    # 策略变量
    longStop = {}
    longexit = {}
    shortStop = {}
    shortexit = {}

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'Window1',
                 'Window2',
                 'trailingPercent',
                 'fixsize',
                 'stopRatio',
                 'profitMultiplier1',
                 'profitMultiplier2']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'trend',
               'mean',
               'cross']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict'
                ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""

        super(macd002_Strategy, self).__init__(ctaEngine, setting)

        # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略%s：初始化' % self.className)

        # self.generateBarDict(self.onBar, 30, self.on30MinBar, self.Window4+20)
        self.trend = {s: 0 for s in self.symbolList}
        self.cross = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 0 for s in self.symbolList}
        self.longStop = {s: 0 for s in self.symbolList}
        self.longexit = {s: 0 for s in self.symbolList}
        self.shortStop = {s: 0 for s in self.symbolList}
        self.shortexit = {s: 0 for s in self.symbolList}

        self.setArrayManagerSize(100)

        self.mail("macd002_Strategy initial！！Goodluck to me~~")
        self.putEvent()
        '''
        在点击初始化策略时触发,载入历史数据,会推送到onbar去执行updatebar,但此时ctaEngine下单逻辑为False,不会触发下单.
        '''

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略%s：启动' % self.className)
        # self.ctaEngine.loadSyncData(self)    # 加载当前正确的持仓
        self.putEvent()
        '''
        在点击启动策略时触发,此时的ctaEngine会将下单逻辑改为True,此时开始推送到onbar的数据会触发下单.
        '''

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略%s：停止' % self.className)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onRestore(self):
        """从错误状态恢复策略（必须由用户集成实现）"""
        #         self.writeCtaLog(u'策略%s：恢复策略状态成功' % self.Name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        pass

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到1分钟K线推送"""

        symbol = bar.vtSymbol
       
        self.writeCtaLog('onBar:%s'%(bar.__dict__))

        if self.posDict[symbol + "_LONG"] == 0 and self.posDict[symbol + "_SHORT"] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
    
        elif (self.posDict[symbol + "_LONG"] > 0):
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.intraTradeLowDict[symbol] = bar.low
            self.longStop[symbol] = self.transactionPrice[symbol] * (1 - self.profitMultiplier2 * self.stopRatio)
            self.longexit[symbol] = self.transactionPrice[symbol] * (1 + self.profitMultiplier1 * self.stopRatio)

            if bar.close <= self.longStop[symbol]:
                self.cancelAll()
                self.sell(symbol, bar.close, self.posDict[symbol + "_LONG"],  levelRate=20)

            if bar.close > self.longexit[symbol]:
                self.cancelAll()
                self.sell(symbol, bar.close, self.posDict[symbol + "_LONG"],  levelRate=20)

        elif (self.posDict[symbol + "_SHORT"] > 0):
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.intraTradeHighDict[symbol] = bar.high
            self.shortStop[symbol] = self.transactionPrice[symbol] * (1 + self.profitMultiplier2 * self.stopRatio)
            self.shortexit[symbol] = self.transactionPrice[symbol] * (1 - self.profitMultiplier1 * self.stopRatio)

            if bar.close >= self.shortStop[symbol]:
                self.cancelAll()
                self.cover(symbol, bar.close * 1.015, self.posDict[symbol + "_SHORT"],  levelRate=20)
            if bar.close < self.shortexit[symbol]:
                self.cancelAll()
                self.cover(symbol, bar.close, self.posDict[symbol + "_SHORT"],  levelRate=20)
        self.writeCtaLog('%son_1min_bar,time:%s,close:%s,trend:%s,cross:%s,mean:%s,longStop:%s,longexit:%s,shortStop:%s,shortexit:%s'
                         % (symbol, bar.datetime, bar.close, self.trend[symbol], self.cross[symbol],self.mean,self.longStop[symbol],self.longexit[symbol],self.shortStop[symbol],self.shortexit[symbol]))
        self.putEvent()

        # ----------------------------------------------------------------------
    def on15MinBar(self, bar):
        """10分钟K线推送"""
        symbol = bar.vtSymbol

        am15 = self.getArrayManager(symbol, "15m")
        if not am15.inited:
            return
        
        dif,dea,macd = ta.MACD(am15.close)
        std = ta.STDDEV(am15.close,self.Window1)
        bdl = ta.MA(std,self.Window2)*100
        self.mean = bdl[-1]
        if dif[-1]<0:
            self.trend[symbol] = 1
        elif dif[-1]>0:
            self.trend[symbol] = -1
        else:
            self.trend[symbol] = 0

        if macd[-5] < 0 and macd[-2]<macd[-3]<macd[-4]<macd[-5] and macd[-1]>macd[-2]:
            self.cross[symbol] = 1
        elif macd[-5] > 0 and macd[-2]>macd[-3]>macd[-4]>macd[-5] and macd[-1]<macd[-2]:
            self.cross[symbol] = -1
        else:
            self.cross[symbol] = 0

        if (self.cross[symbol] == 1 and self.trend[symbol] == 1 and self.mean<5):
            if (self.posDict[symbol + "_LONG"] == 0) and (self.posDict[symbol + "_SHORT"] == 0):
                self.buy(symbol, bar.close, 2, levelRate=20)

        elif (self.cross[symbol] == -1 and self.trend[symbol] == -1 and self.mean<5):
            if (self.posDict[symbol + "_LONG"] == 0) and (self.posDict[symbol + "_SHORT"] == 0):
                self.short(symbol, bar.close, 2, levelRate=20)

        self.putEvent()

    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        if order.status == STATUS_UNKNOWN:
            self.mail(u"出现未知订单，需要策略师外部干预，ID:%s,symbol:%s,direction:%s,offset:%s"%(order.vtOrderID,order.vtSymbol,order.direction,order.offset))
        if order.thisTradedVolume != 0:
            content = u'成交信息播报，ID:%s,symbol:%s,direction:%s,offset:%s,price:%s'%(order.vtOrderID,order.vtSymbol,order.direction,order.offset,order.price)
            self.mail(content)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        symbol = trade.vtSymbol
        self.transactionPrice[symbol] = trade.price
        self.writeCtaLog('Trader price:%s'%trade.price)
        self.mail("onTrader:%s,%s,%s,%s"%(trade.vtSymbol,trade.price,trade.direction,trade.offset))
        # self.saveSyncData()
        pass

    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass