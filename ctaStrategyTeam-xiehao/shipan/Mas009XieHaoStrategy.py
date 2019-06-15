# coding: utf-8
from __future__ import division
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)
from vnpy.trader.app.ctaStrategy.ctaBarManager import CtaTemplate

from collections import defaultdict
import numpy as np
import talib as ta
import pandas as pd
from datetime import datetime


class Mas_Strategy(CtaTemplate):
    className = 'Mas_Strategy'
    author = 'Sky'
    version = '1.1.13'
    # 策略交易标的
    symbol = EMPTY_STRING
    posDict = {}  # 仓位数据缓存
    eveningDict = {}  # 可平仓量数据缓存
    bondDict = {}  # 保证金数据缓存

    # 策略参数
    Window1 = 20
    Window2 = 60
    Window3 = 70
    Window4 = 90
    flag = 0
    trailingPercent = 4
    fixsize = 300
    prop = 0.5
    prop1 = 0.4
    stopRatio = 0.02  # 止损百分比
    profitMultiplier = 5  # 止盈与止损比例
    transactionPrice = {}  # 记录成交价格
    intraTradeHighDict = {}
    intraTradeLowDict = {}
    firstpos = {}
    trend = {}  # 均线趋势，多头1，空头-1
    wave = {}
    cross = {}
    n = 0
    Ma_exit = {}
    # 策略变量
    longStop = EMPTY_FLOAT
    longexit = EMPTY_FLOAT
    shortStop = EMPTY_FLOAT
    shortexit = EMPTY_FLOAT

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'Window1',
                 'Window2',
                 'Window3',
                 'Window4',
                 'trailingPercent',
                 'fixsize',
                 'prop',
                 'prop1',
                 'stopRatio',
                 'profitMultiplier']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'trend',
               'wave',
               'cross',
               'n']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict'
                ]

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""

        super(Mas_Strategy, self).__init__(ctaEngine, setting)

        # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略%s：初始化' % self.className)

        # self.generateBarDict(self.onBar, 30, self.on30MinBar, self.Window4+20)
        self.trend = {s: 0 for s in self.symbolList}
        self.wave = {s: 0 for s in self.symbolList}
        self.cross = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.Ma_exit = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 0 for s in self.symbolList}
        self.firstpos = {s: 0 for s in self.symbolList}

        self.setArrayManagerSize(160)

        self.mail("sky__MA_Strategy initial！！Goodluck to me~~")
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
       

        # 持有多头仓位
        if self.posDict[symbol + "_LONG"] == 0 and self.posDict[symbol + "_SHORT"] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
        # 洗价器
        elif (self.posDict[symbol + "_LONG"] > 0):
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.intraTradeLowDict[symbol] = bar.low
            self.longStop = self.intraTradeHighDict[symbol] * (1 - self.trailingPercent / 100)
            self.longexit = self.firstpos[symbol] * (1 + self.profitMultiplier * self.stopRatio)
            self.writeCtaLog('longexit:%s,Ma_exit:%s' % (self.longexit, self.Ma_exit[symbol]))
            if self.n<3:
                if (bar.close-self.transactionPrice[symbol])/self.transactionPrice[symbol]>=0.02:
                    self.buy(symbol, bar.close*1.015, self.fixsize*2,  levelRate=20)
                    self.n+=1
            if bar.close <= self.Ma_exit[symbol]:
                self.cancelAll()
                self.sell(symbol, bar.close * 0.985, self.posDict[symbol + "_LONG"],  levelRate=20)
                self.n =0
                self.flag = 1
                self.writeCtaLog('买入价格%s,多头触发出场价格:%s,止损价格:%s'%(self.transactionPrice[symbol],bar.close,self.Ma_exit[symbol]))
            elif bar.close > self.longexit:
                self.cancelAll()
                self.sell(symbol, bar.close * 0.985, self.posDict[symbol + "_LONG"],  levelRate=20)
                self.n = 0
                self.flag = 1
                self.writeCtaLog('买入价格%s,多头触发出场价格:%s,止盈价格:%s'%(self.transactionPrice[symbol],bar.close,self.longexit))
        elif (self.posDict[symbol + "_SHORT"] > 0):
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.intraTradeHighDict[symbol] = bar.high
            self.shortStop = self.intraTradeLowDict[symbol] * (1 + self.trailingPercent / 100)
            self.shortexit = self.firstpos[symbol] * (1 - self.profitMultiplier * self.stopRatio)
            self.writeCtaLog('firstpos%s,shortexit:%s,shortStop:%s' % (self.firstpos[symbol],self.shortexit, self.shortStop))
            if self.n<3:
                if (bar.close-self.transactionPrice[symbol])/self.transactionPrice[symbol]<=-0.02:
                    self.short(symbol,bar.close*0.995, self.fixsize*2,  levelRate=20)
                    self.n+=1
            if bar.close >= self.shortStop:
                self.cancelAll()
                self.cover(symbol, bar.close * 1.02, self.posDict[symbol + "_SHORT"],levelRate=20)
                self.n = 0
                self.flag = 1
                self.writeCtaLog('卖出价格%s,空头触发出场价格:%s,止损价格:%s' % (self.firstpos[symbol],bar.close,self.shortStop))
            elif bar.close < self.shortexit:
                self.cancelAll()
                self.cover(symbol, bar.close * 1.02, self.posDict[symbol + "_SHORT"],  levelRate=20)
                self.n = 0
                self.flag = 1
                self.writeCtaLog('卖出价格%s,空头触发出场价格:%s,止盈价格:%s' % (self.firstpos[symbol],bar.close, self.shortexit))
        self.writeCtaLog('%son_1min_bar,time:%s,close:%s,cross:%s,trend:%s,wave:%s,n:%s'%(symbol,bar.datetime,bar.close,self.cross[symbol],self.trend[symbol],self.wave[symbol],self.n))
        self.putEvent()

        # ----------------------------------------------------------------------

    def on30MinBar(self, bar):
        """60分钟K线推送"""
        symbol = bar.vtSymbol

        am30 = self.getArrayManager(symbol, "30m")
        if not am30.inited:
            return
        

        Ma1 = ta.MA(am30.close, self.Window1)

        Ma2 = ta.MA(am30.close, self.Window2)

        Ma3 = ta.MA(am30.close, self.Window3)

        Ma4 = ta.MA(am30.close, self.Window4)
        self.Ma_exit[symbol] = Ma4[-1]

        maxma = max(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])
        minma = min(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])

        agg = (maxma - minma) / minma * 100
        if agg < self.prop:
            self.trend[symbol] = 1
        else:
            self.trend[symbol] = 0

        change = (am30.close[-1] - am30.close[-2]) / am30.close[-2] * 100
        if change > self.prop1 and change < 0.8:
            self.wave[symbol] = 1
        elif change <= self.prop1:
            self.wave[symbol] = -1
        else:
            self.wave[symbol] = 0

        # 判断买卖
        if Ma1[-1] > Ma1[-2] and am30.close[-1] > Ma1[-1]:
            self.cross[symbol] = 1
        elif Ma1[-1] < Ma1[-2] and am30.close[-1] < Ma1[-1]:
            self.cross[symbol] = -1
        else:
            self.cross[symbol] = 0
        
        # 金叉和死叉的条件是互斥
        if (self.cross[symbol] == 1 and self.trend[symbol] == 1 and self.wave[symbol] == 1):
            # 如果金叉时手头没有持仓，则直接做多
            if (self.posDict[symbol + "_LONG"] == 0) and (self.posDict[symbol + "_SHORT"] == 0):
                self.buy(symbol, bar.close*1.015, self.fixsize, levelRate=20)
                self.writeCtaLog('%sdiscover a long signal,time:%s,bar.close:%s,cross:%s,trend:%s,wave:%s' % (
                    symbol, bar.datetime,bar.close,self.cross[symbol], self.trend[symbol], self.wave[symbol]))
            # 如果有空头持仓，则先平空，再做多
            elif self.posDict[symbol + "_SHORT"] != 0:
                self.cover(symbol, bar.close*1.015, self.fixsize, levelRate=20)
                self.buy(symbol, bar.close*1.015, self.fixsize, levelRate=20)

        # 死叉和金叉相反
        elif (self.cross[symbol] == -1 and self.trend[symbol] == 1 and self.wave[symbol] == -1):
            if (self.posDict[symbol + "_LONG"] == 0) and (self.posDict[symbol + "_SHORT"] == 0):
                self.short(symbol, bar.close*0.985, self.fixsize, levelRate=20)
                self.writeCtaLog('%sdiscover a short signal,time:%s,bar.close:%s,cross:%s,trend:%s,wave:%s' % (
                    symbol, bar.datetime, bar.close, self.cross[symbol], self.trend[symbol], self.wave[symbol]))
            elif self.posDict[symbol + "_LONG"] != 0:
                self.sell(symbol, bar.close*0.985, self.fixsize, levelRate=20)
                self.short(symbol, bar.close*0.985, self.fixsize, levelRate=20)
        self.writeCtaLog('%son30minbar,time:%s,close:%s,cross:%s,trend:%s,wave:%s,n:%s'%(symbol,bar.datetime,bar.close,self.cross[symbol],self.trend[symbol],self.wave[symbol],self.n))


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
        # print("\n\n\n\n stg onTrade", trade.vtSymbol)
        self.transactionPrice[symbol] = trader.price_avg
        if self.flag == 1:
            self.firstpos[symbol] = trade.price_avg
            self.flag = 0
        #print('trade direction', trade.direction, 'offset', trade.offset, 'price', trade.price, trade.dt)
        #         self.writeCtaLog('onTrade price:%s'%trade.price)
        self.writeCtaLog('Trader price:%s'%trade.price_avg)
        self.mail("onTrader:%s,%s,%s,%s"%(trade.vtSymbol,trade.price_avg,trade.direction,trade.offset))
        # self.saveSyncData()
        pass

    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass