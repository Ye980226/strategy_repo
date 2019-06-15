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


class RsiStrategy(CtaTemplate):
    className = 'RsiStrategy'  # 策略和仓位数据表的名称
    author = 'HHH'

    # 策略交易标的
    symbol = EMPTY_STRING  
    posDict = {}  # 仓位数据缓存
    eveningDict = {}  # 可平仓量数据缓存
    bondDict = {}  # 保证金数据缓存

    # 策略参数
    fastWindow = 18     # 快速均线参数
    slowWindow = 23     # 慢速均线参数
    windowLength = 90        # ArrayManager的size   
    rsiLength = 25        # 计算RSI的窗口数
    rsiEntry = 10         # RSI的开仓信号
    trailingPercent = 0.4  # 百分比移动止损
    initDays = 1           # 初始化数据所用的天数
    fixedSize = 1           # 每次交易的数量
    stopRatio = 0.04        # 止损比例
    profitMultiplier = 3

    # 策略变量
    rsiValue = 0                        # RSI指标的数值
    rsiBuy = 0                          # RSI买开阈值
    rsiSell = 0                         # RSI卖开阈值
    intraTradeHigh = 0                  # 移动止损用的持仓期内最高价
    intraTradeLow = 0                   # 移动止损用的持仓期内最低价
    Trend = 0                           # 判断趋势
    transactionPrice = 0                # 成交价格
    TorR = 0                            # 止盈或止损后信号改变才交易（用于过滤信号）
    
    initbars = 100  # 获取历史数据的条数
    posSize= 1
    flag = 0
    fastMa0 = EMPTY_FLOAT  # 当前最新的快速EMA
    fastMa1 = EMPTY_FLOAT  # 上一根的快速EMA
    slowMa0 = EMPTY_FLOAT  # 当前最新的慢速EMA
    slowMa1 = EMPTY_FLOAT  # 上一根的慢速EMA
    maTrend = 0  # 均线趋势，多头1，空头-1
    transactionPrice = EMPTY_FLOAT  # 记录成交价格
    fixedSize = 1
    longStop = EMPTY_FLOAT
    shortStop = EMPTY_FLOAT

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'rsiLength',
                 'rsiEntry',
                 'fastWindow',
                 'slowWindow',
                 'stopRatio',
                 'profitMultiplier']   

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'posSize',
               'rsiValue',
               'rsiBuy',
               'rsiSell',
               'transactionPrice',
               'Trend',
               'TorR'] 

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""

        super(RsiStrategy, self).__init__(ctaEngine, setting)
        
        self.rsiBuy = 50 + self.rsiEntry
        self.rsiSell = 50 - self.rsiEntry
        
        self.intraTradeHighDict = {}
        self.intraTradeLowDict = {}
        # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
#         self.writeCtaLog(u'策略%s：初始化' % self.className)
        self.symbol = self.symbolList[0]  
        
        self.generateBarDict(self.onBar)  
        self.generateBarDict(self.onBar,60,self.on60MinBar,size =100)
        self.generateBarDict(self.onBar,15,self.on15MinBar,size =100)
        if self.ctaEngine.engineType == 'trading':
            # 实盘载入1分钟历史数据，并采用回放计算的方式初始化策略参数
            # 通用可选参数：["1min","5min","15min","30min","60min","4hour","1day","1week","1month"]
            pastbar1 = self.loadHistoryBar(self.Symbol,
                                type_ = "1min",  size = 1000)


            # 更新数据矩阵(optional)
            for bar1 in zip (pastbar1):    
                self.amDict[self.symbol].updateBar(bar1)    
        
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

        self.writeCtaLog('stg_onbar_check_%s_%s_%s'%(bar.vtSymbol,bar.datetime,bar.close))
        
        self.bg60Dict[bar.vtSymbol].updateBar(bar)
        self.bg15Dict[bar.vtSymbol].updateBar(bar)


        # 洗价器
        if (self.posDict[self.symbol+"_LONG"] > 0):
            if (bar.close < self.transactionPrice * (1 - self.stopRatio)) or (
                    bar.close > self.transactionPrice * (1 + self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.sell(self.symbol, bar.close*0.98, self.fixedSize, priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                self.TorR = 1
                self.onStop()
#                 self.writeCtaLog('平多仓 止盈或止损')
        elif (self.posDict[self.symbol+"_SHORT"] > 0):
            if (bar.close > self.transactionPrice * (1 + self.stopRatio)) or (
                    bar.close < self.transactionPrice * (1 - self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.cover(self.symbol, bar.close*1.02 , self.fixedSize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                self.TorR = -1
                self.onStop()
#                 self.writeCtaLog('平空仓 止盈或止损')
            
        self.putEvent()

        # ----------------------------------------------------------------------
    def on60MinBar(self, bar):
            """60分钟K线推送"""

            self.am60Dict[bar.vtSymbol].updateBar(bar)
            am60 = self.am60Dict[self.symbol]

            # 计算均线并判断趋势
            fastMa = ta.MA(am60.close, self.fastWindow)
            slowMa = ta.MA(am60.close, self.slowWindow)

            if fastMa[-1] > slowMa[-1]:
                self.Trend = 1
            else:
                self.Trend = -1

            # ----------------------------------------------------------------------
    def on15MinBar(self, bar):
            """收到Bar推送（必须由用户继承实现）"""
            self.am15Dict[bar.vtSymbol].updateBar(bar)
        
            am15 = self.am15Dict[self.symbol]
            rsiValue = ta.RSI(am15.close, self.rsiLength)
            
            if self.TorR == 0:
                if (self.posDict[self.symbol+"_LONG"] == 0) and (self.posDict[self.symbol+"_SHORT"] == 0):
#                     self.writeCtaLog('signa aa[-1]:%s, aa[-5]:%s,aa[-10]:%s,aa[-15]:%s,crossOver:%s,crossBelow:%s'%(aa[-1],aa[-5],aa[-10],aa[-15],crossOver,crossBelow))
                    if self.Trend==1:
                        if rsiValue[-1] < self.rsiSell and rsiValue[-5] >= self.rsiSell:
                            self.buy(self.symbol, bar.close*1.02 , self.fixedSize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                    elif self.Trend==-1:
                        if rsiValue[-1] > self.rsiBuy and rsiValue[-5] <= self.rsiBuy:
                            self.short(self.symbol, bar.close*0.98, self.fixedSize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
            elif self.TorR == 1:
                if rsiValue[-1] > self.rsiSell:
                    self.TorR = 0
        
            # 上次空头止盈或止损
            elif self.TorR == -1:
                if rsiValue[-1] < self.rsiBuy:
                    self.TorR = 0
                        
            
            # 发出状态更新事件
            self.putEvent()

            # ----------------------------------------------------------------------



    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""

        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        #print("\n\n\n\n stg onTrade", trade.vtSymbol)
        self.transactionPrice = trade.price
#         print('trade direction',trade.direction,'offset',trade.offset,'price',trade.price, trade.dt)

#         self.writeCtaLog('onTrade price:%s'%trade.price)
        # self.saveSyncData()
        pass

    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass 