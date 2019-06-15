# coding: utf-8
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate,
                                                     BarGenerator,
                                                     ArrayManager)

from collections import defaultdict
import numpy as np
import talib as ta
import pandas as pd
from datetime import datetime


class Mas_Strategy(CtaTemplate):
    className = 'Mas_Strategy'
    author = 'Sky'

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

    trailingPercent = 4
    fixsize = 1
    prop = 0.79
    prop1 = 0.35
    stopRatio = 0.02  # 止损百分比
    profitMultiplier = 6  # 止盈与止损比例
    transactionPrice = {}  # 记录成交价格
    intraTradeHighDict = {}
    intraTradeLowDict = {}
    trend = {}  # 均线趋势，多头1，空头-1
    wave = {}
    cross = {}
    Ma_exit = {}
    # 策略变量
    initbars = 100  # 获取历史数据的条数
    fastMa0 = EMPTY_FLOAT
    fastMa1 = EMPTY_FLOAT
    Ma1 = EMPTY_FLOAT
    Ma2 = EMPTY_FLOAT
    Ma3 = EMPTY_FLOAT
    Ma4 = EMPTY_FLOAT

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
               'posSize',
               'fastMa0',
               'fastMa1',
               'Ma1',
               'Ma2',
               'Ma3',
               'Ma4',
               'trend',
               'wave']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""

        super(Mas_Strategy, self).__init__(ctaEngine, setting)

        # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        #         self.writeCtaLog(u'策略%s：初始化' % self.className)
        self.trend = {s: 0 for s in self.symbolList}
        self.wave = {s: 0 for s in self.symbolList}
        self.cross = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.Ma_exit = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 0 for s in self.symbolList}

        self.generateBarDict(self.onBar)
        self.generateBarDict(self.onBar, 30, self.on30MinBar, size=100)
        if self.ctaEngine.engineType == 'trading':
            pastBarDict = {s + "1min": self.loadHistoryBar(s, type_="1min", size=1200) for s in self.symbolList}
            pastBar30Dict = {s + "30min": self.loadHistoryBar(s, type_="30min", size=1000)[:-20] for s in
                             self.symbolList}
            bar30Dict = {s: pastBar30Dict[s + '30min'] for s in self.symbolList}
            for s in self.symbolList:
                for bar in bar30Dict[s]:
                    self.am30Dict[s].updateBar(bar)

            barDict = {s: pastBarDict[s + '1min'] for s in self.symbolList}
            for s in self.symbolList:
                for bar in barDict[s]:
                    self.onBar(bar)

        elif self.ctaEngine.engineType == 'backtesting':
            # 获取回测设置中的initHours长度的历史数据
            self.initBacktesingData()
        self.putEvent()
        '''
        在点击初始化策略时触发,载入历史数据,会推送到onbar去执行updatebar,但此时ctaEngine下单逻辑为False,不会触发下单.
        '''

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        #         self.writeCtaLog(u'策略%s：启动' % self.className)
        # self.ctaEngine.loadSyncData(self)    # 加载当前正确的持仓
        self.putEvent()
        '''
        在点击启动策略时触发,此时的ctaEngine会将下单逻辑改为True,此时开始推送到onbar的数据会触发下单.
        '''

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        #         self.writeCtaLog(u'策略%s：停止' % self.className)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onRestore(self):
        """从错误状态恢复策略（必须由用户集成实现）"""
        #         self.writeCtaLog(u'策略%s：恢复策略状态成功' % self.Name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        self.bgDict[tick.vtSymbol].updateTick(tick)
        pass

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到1分钟K线推送"""
        self.cancelAll()
        # 基于60分钟判断趋势过滤，因此先更新
        symbol = bar.vtSymbol
        self.writeCtaLog('stg_onbar_check_%s_%s_%s' % (bar.vtSymbol, bar.datetime, bar.close))

        self.bg30Dict[bar.vtSymbol].updateBar(bar)
        am = self.amDict[symbol]

        # 持有多头仓位
        if self.posDict[symbol + "_LONG"] == 0 and self.posDict[symbol + "_SHORT"] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
        # 洗价器
        elif (self.posDict[symbol + "_LONG"] > 0):
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.intraTradeLowDict[symbol] = bar.low
            self.longStop = self.intraTradeHighDict[symbol] * (1 - self.trailingPercent / 100)
            #             print('最高价:%s'%self.intraTradeHighDict[symbol])
            #             print('止损价格:%s'%self.longStop)
            #             print('开仓价格:%s'%self.transactionPrice)
            if (bar.close <= self.Ma_exit[symbol]) or (
                    bar.close > self.transactionPrice[symbol] * (1 + self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.sell(symbol, bar.close * 0.98, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)
        #                 self.writeCtaLog('平多仓 止盈或止损')
        elif (self.posDict[symbol + "_SHORT"] > 0):
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.intraTradeHighDict[symbol] = bar.high
            self.shortStop = self.intraTradeLowDict[symbol] * (1 + self.trailingPercent / 100)
            if (bar.close >= self.shortStop) or (
                    bar.close < self.transactionPrice[symbol] * (1 - self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.cover(symbol, bar.close * 1.02, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)

        self.putEvent()

        # ----------------------------------------------------------------------

    def on30MinBar(self, bar):
        """60分钟K线推送"""
        symbol = bar.vtSymbol
        self.am30Dict[bar.vtSymbol].updateBar(bar)

        am30 = self.am30Dict[symbol]

        Ma1 = ta.MA(am30.close, self.Window1)

        self.fastMa0 = Ma1[-1]

        self.fastMa1 = Ma1[-2]

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
        if change > self.prop1:
            self.wave[symbol] = 1
        elif change <= self.prop1:
            self.wave[symbol] = -1
        else:
            self.wave[symbol] = 0

        # 判断买卖
        if Ma1[-1] > Ma1[-2] and self.am30Dict[symbol].close[-1] > Ma1[-1]:
            self.cross[symbol] = 1
        elif Ma1[-1] < Ma1[-2] and self.am30Dict[symbol].close[-1] < Ma1[-1]:
            self.cross[symbol] = -1
        else:
            self.cross[symbol] = 0

        # 金叉和死叉的条件是互斥
        if (self.cross[symbol] == 1 and self.trend[symbol] == 1 and self.wave[symbol] == 1):
            # 如果金叉时手头没有持仓，则直接做多
            if (self.posDict[symbol + "_LONG"] == 0) and (self.posDict[symbol + "_SHORT"] == 0):
                self.buy(symbol, bar.close, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)
            # 如果有空头持仓，则先平空，再做多
            elif self.posDict[symbol + "_SHORT"] == 1:
                self.cover(symbol, bar.close, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)
                self.buy(symbol, bar.close, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)

        # 死叉和金叉相反
        elif (self.cross[symbol] == -1 and self.trend[symbol] == 1 and self.wave[symbol] == -1):
            if (self.posDict[symbol + "_LONG"] == 0) and (self.posDict[symbol + "_SHORT"] == 0):
                self.short(symbol, bar.close, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)
            elif self.posDict[symbol + "_LONG"] == 1:
                self.sell(symbol, bar.close, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)
                self.short(symbol, bar.close, self.fixsize, priceType=PRICETYPE_LIMITPRICE, levelRate=20)
        # ---------------------------------------------------------------------

    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""

        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        symbol = trade.vtSymbol
        # print("\n\n\n\n stg onTrade", trade.vtSymbol)
        self.transactionPrice[symbol] = trade.price
        print('trade direction', trade.direction, 'offset', trade.offset, 'price', trade.price, trade.dt)
        #         self.writeCtaLog('onTrade price:%s'%trade.price)
        # self.saveSyncData()
        pass

    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass