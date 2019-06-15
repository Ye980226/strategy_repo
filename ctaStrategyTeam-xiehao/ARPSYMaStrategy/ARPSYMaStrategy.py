from __future__ import division
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
import pandas as pd
import numpy as np


########################################################################
# 策略继承CtaTemplate
class ARPSYMaStrategy(CtaTemplate):
    """ARPSY均线策略Demo"""
    className = 'ARPSYMaStrategy'
    author = 'Chenziyue'

    # 策略参数
    fastPeriod = 15  # 判断趋势用到的短期均线时间长度
    slowPeriod = 36  # 判断趋势用到的长期均线时间长度
    arPeriod = 15  # AR指标的时间参数
    psyPeriod = 8  # PSY指标的时间参数
    timePeriod = 10  # 均线组的个数
    multiplier = 5  # 长短期乘数
    upperthreshold = 0.6  # 买进的分数门槛
    lowerthreshold = 0.4  # 卖出的分数门槛
    stopRatio = 0.03  # 止损率
    lot = 1  # 设置手数
    # exit = {}
    # 策略变量
    maTrend = {}  # 记录趋势状态，多头1，空头-1
    transactionPrice = {}  # 记录成交价格

    # 参数列表
    paramList = ['fastPeriod',
                 'slowPeriod',
                 'arPeriod',
                 'psyPeriod',
                 'timePeriod',
                 'multiplier',
                 'upperthreshold',
                 'lowerthreshold',
                 'stopRatio',
                 'lot']

    # 变量列表
    varList = ['maTrend',
               'transactionPrice']

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        # 首先找到策略的父类（就是类CtaTemplate），然后把DoubleMaStrategy的对象转换为类CtaTemplate的对象
        super().__init__(ctaEngine, setting)

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        self.setArrayManagerSize(150)
        self.maTrend = {s: 0 for s in self.symbolList}
        self.crossOver = {s: 0 for s in self.symbolList}
        self.crossBelow = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}  # 生成成交价格的字典
        self.exit = {s: 0 for s in self.symbolList}
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
        self.writeCtaLog(u'策略停止')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        pass

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送"""
        self.onBarStopLoss(bar)
        self.onBarExecute(bar)
    # ----------------------------------------------------------------------
    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol

        # 计算止损止盈价位
        longStop = self.transactionPrice[symbol] * (1 - self.stopRatio)
        longProfit = self.transactionPrice[symbol] * (1 + 3 * self.stopRatio)
        shortStop = self.transactionPrice[symbol] * (1 + self.stopRatio)
        shortProfit = self.transactionPrice[symbol] * (1 - 3 * self.stopRatio)

        # 洗价器
        if (self.posDict[symbol + '_LONG'] > 0):
            # if self.exit[symbol] == 1:
            #     self.sell(symbol, bar.close, self.posDict[symbol + '_LONG'])
            if (bar.close < longStop):
                # print('LONG stopLoss')
                self.cancelAll()
                self.sell(symbol, bar.close, self.posDict[symbol + '_LONG'])

            elif (bar.close > longProfit):
                # print('LONG takeProfit')
                self.cancelAll()
                self.sell(symbol, bar.close, self.posDict[symbol + '_LONG'])

        elif (self.posDict[symbol + '_SHORT'] > 0):
            # if self.exit[symbol] == -1:
            #     self.cover(symbol, bar.close, self.posDict[symbol + '_SHORT'])
            if (bar.close > shortStop):
                # print('SHORT stopLoss')
                self.cancelAll()
                self.cover(symbol, bar.close, self.posDict[symbol + '_SHORT'])
            elif (bar.close < shortProfit):
                # print('SHORT takeProfit')
                self.cancelAll()
                self.cover(symbol, bar.close, self.posDict[symbol + '_SHORT'])

    # ----------------------------------------------------------------------

    def onBarExecute(self, bar):
        symbol = bar.vtSymbol
        pass
                
    def on60MinBar(self, bar):
        """收到60分钟Bar推送"""
        symbol = bar.vtSymbol

        am60 = self.getArrayManager(symbol, "60m")  # 获取历史数组

        if not am60.inited:
            return

        # 计算均线并判断趋势-------------------------------------------------
        fastMa = ta.MA(am60.close, self.fastPeriod)
        slowMa = ta.MA(am60.close, self.slowPeriod)

        if (fastMa[-1] > slowMa[-1]) and (fastMa[-2] < slowMa[-2]):
            self.maTrend[symbol] = 1
        elif (fastMa[-1] < slowMa[-1]) and (fastMa[-2] > slowMa[-2]):
            self.maTrend[symbol] = -1
        else:
            self.maTrend[symbol] = self.maTrend[symbol]

        # 计算策略需要的信号-------------------------------------------------
        def calculate(factor, t):
            mas = ta.MA(factor, t)
            mal = ta.MA(factor, self.multiplier * t)
            df = np.vstack((mas, mal))
            scoretable = np.array(list(map(lambda s, l: 1 if s > l else 0, df[0, :], df[1, :])))
            return scoretable

        ar = ta.SUM(am60.high[1:] - am60.open[1:], self.arPeriod) / ta.SUM(am60.open[1:] - am60.low[1:], self.arPeriod)
        x = range(1, self.timePeriod + 1, 1)
        arscore = np.array([calculate(ar, t) for t in x]).transpose().sum(axis=1)

        psy = ta.SUM(np.array(am60.close[1:] > am60.close[:-1], dtype='double'), self.psyPeriod) / self.psyPeriod
        psyscore = np.array([calculate(psy, t) for t in x]).transpose().sum(axis=1)

        score = arscore + psyscore

        self.crossOver[symbol] = (score[-1] > 2 * self.timePeriod * self.upperthreshold) and (
                    score[-2] < 2 * self.timePeriod * self.upperthreshold)
        self.crossBelow[symbol] = (score[-1] < 2 * self.timePeriod * self.lowerthreshold) and (
                    score[-2] > 2 * self.timePeriod * self.lowerthreshold)
        if (self.crossOver[symbol]) and (self.maTrend[symbol] == 1) and (self.posDict[symbol + '_LONG'] < 5):
            # 如果没有空头持仓，则直接做多
            if self.posDict[symbol + '_SHORT'] == 0:
                self.cancelAll()
                self.buy(symbol, bar.close * 1.05, self.lot)
               
            # 如果有空头持仓，则先平空，再做多
            elif self.posDict[symbol + '_SHORT'] > 0:
                self.cancelAll()
                self.cover(symbol, bar.close * 1.05, self.posDict[symbol + '_SHORT'])
                self.buy(symbol, bar.close * 1.05, self.lot)
        
        # 如果死叉出现，趋势向下
        elif (self.crossBelow[symbol]) and (self.maTrend[symbol] == 1) and (self.posDict[symbol + '_SHORT'] < 5):
            if self.posDict[symbol + '_LONG'] == 0:
                self.cancelAll()
                self.short(symbol, bar.close * 0.95, self.lot)
         
            elif self.posDict[symbol + '_LONG'] > 0:
                self.cancelAll()
                self.sell(symbol, bar.close * 0.95, self.posDict[symbol + '_LONG'])
                self.short(symbol, bar.close * 0.95, self.lot)
        
        self.writeCtaLog(u'on60MinBar,datetime:%s,score-1:%s,score-2:%s,crossOver:%s,crossBelow:%s,maTrend:%s'
             % (bar.datetime,score[-1], score[-2], self.crossOver[symbol],self.crossBelow[symbol],self.maTrend[symbol]))
        
        # 发出状态更新事件
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送"""
        symbol = trade.vtSymbol
        if trade.offset == OFFSET_OPEN:  # 判断成交订单类型
            self.transactionPrice[symbol] = trade.price  # 记录成交价格

    # ----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass