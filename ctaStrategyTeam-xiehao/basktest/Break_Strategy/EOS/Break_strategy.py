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


class break_Strategy(CtaTemplate):
    className = 'break_Strategy'
    author = 'Sky'

    # 策略交易标的
    symbol = EMPTY_STRING  
    posDict = {}  # 仓位数据缓存
    eveningDict = {}  # 可平仓量数据缓存
    bondDict = {}  # 保证金数据缓存

    # 策略参数
    Window1 = 12   # 快速均线参数
    Window2 = 17    # 慢速均线参数
    breakday = 5
    ccivalue = 8
    initDays = 1       # 初始化数据所用的天数
    fixsize = 1
    cciPeriod = 16
    trailingPercent = 7
    profitMultiplier = 4
    # 策略变量
    longStop = EMPTY_FLOAT
    shortStop = EMPTY_FLOAT
    stopRatio = 0.02
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'Window1',
                 'Window2',
                'breakday',
                'ccivalue',
                'initDays',
                'fixedSize',
                'cciPeriod',
                'trailingPercent',
                'longStop',
                'shortStop',
                'profitMultiplier',
                'stopRatio']  

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'posSize',
               'H20',
               'L20',
                'shortStop',
                'longStop']  

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""

        super(break_Strategy, self).__init__(ctaEngine, setting)
        
        self.intraTradeHighDict = {}
        self.intraTradeLowDict = {}
        self.RSI = 0
        self.CCI = 0
        self.MA = 0
        self.Break = 0
        # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
#         self.writeCtaLog(u'策略%s：初始化' % self.className)
        self.symbol = self.symbolList[0]  
        
        self.generateBarDict(self.onBar)  
        self.generateBarDict(self.onBar,15,self.on15MinBar,size =100)
        self.generateBarDict(self.onBar,60,self.on60MinBar,size =100)
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
        
        self.bg15Dict[bar.vtSymbol].updateBar(bar)
        self.bg60Dict[bar.vtSymbol].updateBar(bar)
        am = self.amDict[self.symbol]
        
        # 持有多头仓位
        if self.posDict[self.symbol+"_LONG"] == 0 and self.posDict[self.symbol+"_SHORT"] == 0:
            self.intraTradeHighDict[self.symbol] = 0
            self.intraTradeLowDict[self.symbol] = 999999
        # 洗价器
        elif (self.posDict[self.symbol+"_LONG"] > 0):
            self.intraTradeHighDict[self.symbol] = max(self.intraTradeHighDict[self.symbol], bar.high)
            self.intraTradeLowDict[self.symbol] = bar.low
            self.longStop = self.intraTradeHighDict[self.symbol]*(1-self.trailingPercent/100)
#             print('最高价:%s'%self.intraTradeHighDict[symbol])
#             print('止损价格:%s'%self.longStop)
#             print('开仓价格:%s'%self.transactionPrice)
            if (bar.close<=self.longStop) or (bar.close > self.transactionPrice * (1 + self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.sell(self.symbol, bar.close*0.98, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
#                 self.writeCtaLog('平多仓 止盈或止损')
        elif (self.posDict[self.symbol+"_SHORT"] > 0):
            self.intraTradeLowDict[self.symbol] = min(self.intraTradeLowDict[self.symbol], bar.low)
            self.intraTradeHighDict[self.symbol] = bar.high
            self.shortStop = self.intraTradeLowDict[self.symbol]*(1+self.trailingPercent/100)
            if (bar.close>=self.shortStop) or (bar.close < self.transactionPrice * (1 - self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.cover(self.symbol, bar.close*1.08, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
            
        self.putEvent()

        # ----------------------------------------------------------------------
    def on15MinBar(self, bar):
            """60分钟K线推送"""
            self.am15Dict[bar.vtSymbol].updateBar(bar)
            
            am30 = self.am15Dict[self.symbol]
            cci = ta.CCI(am30.high, am30.low, am30.close, self.cciPeriod)
            
            if cci[-1]>self.ccivalue:
                self.CCI = 1
            elif cci[-1]<-self.ccivalue:
                self.CCI = -1
            else:
                self.CCI = 0
            ##  30分钟周期计算通道突破    
            HH = ta.MAX(am30.high,self.breakday)
            LL = ta.MIN(am30.low,self.breakday)
            if am30.close[-1]>HH[-2]:
                self.Break = 1
            elif am30.close[-1]<LL[-2]:
                self.Break = -1

#         ma1 = ta.EMA(am30.close,self.Window1)
#         ma2 = ta.EMA(am30.close,self.Window2)
        
#         if ma1[-1]>ma2[-1]:
#             self.MA = 1
#         elif ma1[-1]<ma2[-1]:
#             self.MA = -1

    def on60MinBar(self, bar):
            """60分钟K线推送"""
            self.am60Dict[bar.vtSymbol].updateBar(bar)
            
            am60 = self.am60Dict[self.symbol]

            ma1 = ta.MA(am60.close,self.Window1)
            ma2 = ta.MA(am60.close,self.Window2)
            
            if ma1[-1]>ma2[-1]:
                self.MA = 1
            elif ma1[-1]<ma2[-1]:
                self.MA = -1
        
#         HH = ta.MAX(am60.high,self.breakday)
#         LL = ta.MIN(am60.low,self.breakday)
#         if am60.close[-1]>HH[-2]:
#             self.Break = 1
#         elif am60.close[-1]<LL[-2]:
#             self.Break = -1
        
        ## 信号取和
            Signal = self.Break+self.CCI+self.MA
            
            ##开平仓
            if Signal>=2:
                if (self.posDict[self.symbol+"_LONG"]==0) and (self.posDict[self.symbol+"_SHORT"]==0):
                    self.buy(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                elif self.posDict[self.symbol+"_SHORT"] > 0:
                    self.cancelAll()
                    self.cover(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                    self.buy(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                
            elif Signal<=-2:
                if (self.posDict[self.symbol+"_LONG"]==0) and (self.posDict[self.symbol+"_SHORT"]==0):
                    self.short(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                elif self.posDict[self.symbol+"_LONG"] == 1:
                    self.sell(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                    self.short(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)


    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""

        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        #print("\n\n\n\n stg onTrade", trade.vtSymbol)
        self.transactionPrice = trade.price
        #print('trade direction',trade.direction,'offset',trade.offset,'price',trade.price, trade.dt)
#         self.writeCtaLog('onTrade price:%s'%trade.price)
        # self.saveSyncData()
        pass

    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass