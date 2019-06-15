from __future__ import division
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)
from collections import defaultdict
import numpy as np
import talib as ta
import pandas as pd
from datetime import datetime


########################################################################
# 策略继承CtaTemplate
class sky1_Strategy(CtaTemplate):
    className = 'sky1_Strategy'
    author = 'xh'

    # 策略交易标的的列表
    symbol = EMPTY_STRING  # 初始化
    tradeSymbol = EMPTY_STRING

    posDict = {}  # 仓位数据缓存
    eveningDict = {}  # 可平仓量数据缓存
    bondDict = {}  # 保证金数据缓存

    initDays = 1
    # 策略参数
    Window1 = 20
    Window2 = 40
    Window3 = 60
    Window4 = 90
    initDays = 2  # 初始化数据所用的天数
    trailingPercent = 4
    fixsize = 2
    prop = 0.79
    prop1 = 0.35
    stopRatio = 0.02  # 止损百分比
    profitMultiplier = 6  # 止盈与止损比例

    # 策略变量
    transactionPrice = EMPTY_FLOAT  # 记录成交价格
    initbars = 100  # 获取历史数据的条数
    fastMa0 = EMPTY_FLOAT
    fastMa1 = EMPTY_FLOAT
    Ma1 = EMPTY_FLOAT
    Ma2 = EMPTY_FLOAT
    Ma3 = EMPTY_FLOAT
    Ma4 = EMPTY_FLOAT
    trend = 0  # 均线趋势，多头1，空头-1
    wave = 0
    cross=0
    Ma_exit = EMPTY_FLOAT
    longStop = EMPTY_FLOAT
    shortStop = EMPTY_FLOAT

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'symbolList',
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
               'transactionPrice',
               'fastMa0',
               'fastMa1',
               'trend',
               'wave',
               'cross',
               'Ma_exit',
               'longStop',
               'shortStop']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict', 'bondDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):

        # 首先找到策略的父类（就是类CtaTemplate），然后把DoubleMaStrategy的对象转换为类CtaTemplate的对象
        super(sky1_Strategy, self).__init__(ctaEngine, setting)

        self.intraTradeHighDict = {}
        self.intraTradeLowDict = {}


    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""

        self.tradeSymbol = self.symbol = self.symbolList[0]

        # 构造K线合成器对象
        self.generateBarDict(self.onBar)  
        self.generateBarDict(self.onBar,30,self.on30MinBar,size =10)

        # 对于高频交易员，提供秒级别的 Bar，或者可当作秒级计数器，参数为秒，可在 onHFBar() 获取
        self.generateHFBar(10)

        # 回测和实盘的获取历史数据部分，建议实盘初始化之后得到的历史数据和回测预加载数据交叉验证，确认代码正确
        if self.ctaEngine.engineType == 'trading':
            # 实盘载入1分钟历史数据，并采用回放计算的方式初始化策略参数
            # 通用可选参数：["1min","5min","15min","30min","60min","4hour","1day","1week","1month"]
            pastbar1 = self.loadHistoryBar(self.symbol,
                                type_ = "1min",  size = 1000)
            pastbar2 = self.loadHistoryBar(self.symbol,
                            type_ = "30min",  size = 1000)

            # 更新数据矩阵(optional)
            for bar1,bar2 in zip(pastbar1,pastbar2):    
                self.amDict[self.symbol].updateBar(bar1)    
                self.amDict[self.symbol].updateBar(bar2)
        
        elif self.ctaEngine.engineType == 'backtesting':
            # 获取回测设置中的initHours长度的历史数据
            self.initBacktesingData()    
        self.putEvent()  # putEvent 能刷新UI界面的信息

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.mail("stg_xh: start")
        # self.writeCtaLog(u'xh谢昊1策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        # self.writeCtaLog(u'xh谢昊1策略停止')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        # if tick.vtSymbol == self.tradeSymbol:
        #     return
        self.bgDict[tick.vtSymbol].updateTick(tick)
        self.hfDict[tick.vtSymbol].updateTick(tick)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onHFBar(self,bar):
        """收到高频bar推送（需要在onInit定义频率，否则默认不推送）"""
        # self.writeCtaLog('stg_onHFbar_check_%s_%s_%s'%(bar.vtSymbol,bar.datetime,bar.close))
    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # if bar.vtSymbol == self.tradeSymbol:
        #     return

        self.bg30Dict[self.symbol].updateBar(bar)

        if self.posDict[self.tradeSymbol+"_LONG"] == 0 and self.posDict[self.tradeSymbol+"_SHORT"] == 0:
            self.intraTradeHighDict[self.tradeSymbol] = 0
            self.intraTradeLowDict[self.tradeSymbol] = 999999

        # 持有多头仓位
        elif self.posDict[self.tradeSymbol+"_LONG"] >0:
            self.intraTradeHighDict[self.tradeSymbol] = max(self.intraTradeHighDict[self.tradeSymbol], bar.high)
            self.intraTradeLowDict[self.tradeSymbol] = bar.low
            self.longStop = self.intraTradeHighDict[self.tradeSymbol]*(1-self.trailingPercent/100)
            self.lone_exit = self.transactionPrice * (1 + self.profitMultiplier * self.stopRatio)
            self.writeCtaLog('多头止损价格:%s'%self.longStop)
            self.writeCtaLog('多头止盈价格:%s'%self.lone_exit)
            if bar.close<=self.longStop:
                self.cancelAll()
                self.sell(self.tradeSymbol, bar.close*0.98, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
            self.writeCtaLog('出场价格:%s' %self.transactionPrice)

#         # 持有空头仓位，字典保存最低价，计算止盈与止损
        elif self.posDict[self.tradeSymbol+"_SHORT"] >0:
            self.intraTradeLowDict[self.tradeSymbol] = min(self.intraTradeLowDict[self.tradeSymbol], bar.low)
            self.intraTradeHighDict[self.tradeSymbol] = bar.high
            self.shortStop = self.intraTradeLowDict[self.tradeSymbol]*(1+self.trailingPercent/100)
            self.shortexit = self.transactionPrice * (1 - self.profitMultiplier * self.stopRatio)
            self.writeCtaLog('空头止损价格:%s' % self.shortStop)
            self.writeCtaLog('空头止盈价格:%s' % self.shortexit)
            if bar.close>=self.shortStop:
                self.cancelAll()
                self.cover(self.tradeSymbol, bar.close*1.02, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
            self.writeCtaLog('出场价格:%s' % self.transactionPrice)

        self.writeCtaLog('stg_xhonBar: symbol:%s,time:%s,close:%s,cross:%s,trend :%s,wave:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.cross,self.trend, self.wave))

    def on30MinBar(self, bar):
        self.writeCtaLog('stg_on30Minbar_check_%s_%s_%s'%(bar.vtSymbol,bar.datetime,self.am30Dict[bar.vtSymbol].close))
        self.am30Dict[bar.vtSymbol].updateBar(bar)
        Ma1 = ta.MA(self.am30Dict[bar.vtSymbol].close, self.Window1)

        self.fastMa0 = Ma1[-1]

        self.fastMa1 = Ma1[-2]

        Ma2 = ta.MA(self.am30Dict[bar.vtSymbol].close, self.Window2)

        Ma3 = ta.MA(self.am30Dict[bar.vtSymbol].close, self.Window3)

        Ma4 = ta.MA(self.am30Dict[bar.vtSymbol].close, self.Window4)
        self.Ma_exit = Ma4[-1]

        maxma = max(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])
        minma = min(Ma1[-1], Ma2[-1], Ma3[-1], Ma4[-1])

        agg = (maxma - minma) / minma * 100
        self.writeCtaLog('on30Min:time:%s,agg:%s,self.prop:%s' % (bar.datetime,agg, self.prop))
        if agg < self.prop:
            self.trend = 1
        else:
            self.trend = 0

        change = (self.am30Dict[bar.vtSymbol].close[-1] - self.am30Dict[bar.vtSymbol].close[-2]) / self.am30Dict[bar.vtSymbol].close[-2] * 100
        self.writeCtaLog('on30Min:time:%s,change:%s,self.prop1:%s' % (bar.datetime,change, self.prop1))
        if change > self.prop1:
            self.wave = 1
        elif change <= self.prop1:
            self.wave = -1
        else:
            self.wave = 0

        # 判断买卖
        if self.fastMa0 > self.fastMa1 and self.am30Dict[bar.vtSymbol].close[-1] > self.fastMa0:
                self.cross = 1
        elif self.fastMa0 < self.fastMa1 and self.am30Dict[bar.vtSymbol].close[-1] < self.fastMa0:
                self.cross = -1
        else:
                self.cross = 0
        self.writeCtaLog('on30Min:time:%s,cross:%s' % (bar.datetime, self.cross))
        
        
        # 金叉和死叉的条件是互斥
        if (self.cross ==1 and self.trend == 1 and self.wave == 1):
            # 如果金叉时手头没有持仓，则直接做多
            if (self.posDict[self.tradeSymbol + "_LONG"] == 0) and (self.posDict[self.tradeSymbol + "_SHORT"] == 0):
                self.writeCtaLog('开多仓: symbol:%s,time:%s,close:%s,cross:%s,trend :%s,wave:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.cross, self.trend, self.wave))
                self.buy(self.tradeSymbol, bar.close*1.02, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
            # 如果有空头持仓，则先平空，再做多
            elif self.posDict[self.tradeSymbol + "_SHORT"] == 1:
                self.cover(self.tradeSymbol, bar.close*1.02, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
                self.writeCtaLog('平空开多仓: symbol:%s,time:%s,close:%s,cross:%s,trend :%s,wave:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.cross, self.trend, self.wave))
                self.buy(self.tradeSymbol, bar.close*1.02, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
                self.writeCtaLog('discover a buy signal')

        # 死叉和金叉相反
        elif (self.cross ==-1 and self.trend == 1 and self.wave == 1):
            if (self.posDict[self.tradeSymbol + "_LONG"] == 0) and (self.posDict[self.tradeSymbol + "_SHORT"] == 0):
                self.writeCtaLog('开空仓: time:%s,symbol:%s,close:%s,cross:%s,trend :%s,wave:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.cross, self.trend, self.wave))
                self.short(self.tradeSymbol, bar.close*0.98, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
            elif self.posDict[self.tradeSymbol + "_LONG"] == 1:
                self.sell(self.tradeSymbol, bar.close*0.98, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
                self.writeCtaLog('平多开空仓:time:%s,symbol:%s,close:%s,cross:%s,trend :%s,wave:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.cross, self.trend, self.wave))
                self.short(self.tradeSymbol, bar.close*0.98, self.fixsize, priceType = PRICETYPE_MARKETPRICE, levelRate=20)
                self.writeCtaLog('discover a short signal')

        # 发出状态更新事件
        self.putEvent()


    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        self.transactionPrice = trade.price
        self.writeCtaLog('onTrade price:%s' % trade.price)
        self.mail('stg_xhontrade: %s,%s,%s,%s' % (trade.vtSymbol, trade.price, trade.direction, trade.offset))

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass