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
    initDays = 2       # 初始化数据所用的天数
    trailingPercent = 4
    fixsize = 1
    prop = 0.79
    prop1 = 0.35
    stopRatio = 0.02       # 止损百分比
    profitMultiplier = 8   # 止盈与止损比例

    # 策略变量
    initbars = 100  # 获取历史数据的条数
    fastMa0 = EMPTY_FLOAT  
    fastMa1 = EMPTY_FLOAT   
    Ma1 = EMPTY_FLOAT 
    Ma2 = EMPTY_FLOAT   
    Ma3 = EMPTY_FLOAT
    Ma4 = EMPTY_FLOAT
    trend = 0             # 均线趋势，多头1，空头-1
    wave = 0
    Ma_exit = EMPTY_FLOAT 
    
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
        
        self.intraTradeHighDict = {}
        self.intraTradeLowDict = {}
        # ----------------------------------------------------------------------

    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
#         self.writeCtaLog(u'策略%s：初始化' % self.className)
        self.symbol = self.symbolList[0]  
        
        self.generateBarDict(self.onBar)  
        self.generateBarDict(self.onBar,30,self.on30MinBar,size =100)
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
        
        self.bg30Dict[bar.vtSymbol].updateBar(bar)
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
            if (bar.close<=self.Ma_exit) or (bar.close > self.transactionPrice * (1 + self.profitMultiplier * self.stopRatio)):
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
    def on30MinBar(self, bar):
            """60分钟K线推送"""
            self.am30Dict[bar.vtSymbol].updateBar(bar)
        
            am30 = self.am30Dict[self.symbol]
            Ma1 = ta.MA(am30.close, self.Window1)
        
            self.fastMa0 = Ma1[-1]

            self.fastMa1 = Ma1[-2]

            Ma2 = ta.MA(am30.close, self.Window2)

            Ma3 = ta.MA(am30.close, self.Window3)

            Ma4 = ta.MA(am30.close, self.Window4)
            self.Ma_exit = Ma4[-1]

            maxma = max(Ma1[-1],Ma2[-1],Ma3[-1],Ma4[-1])
            minma = min(Ma1[-1],Ma2[-1],Ma3[-1],Ma4[-1])

            agg = (maxma-minma)/minma*100
            if agg<self.prop:
                self.trend = 1
            else:
                self.trend = 0

            change = (am30.close[-1]-am30.close[-2])/am30.close[-2]*100
            if change>self.prop1:
                self.wave = 1
            elif change<=self.prop1:
                self.wave = -1
            else:
                self.wave = 0




            # 判断买卖
            crossOver = (self.fastMa0>self.fastMa1 and am30.close[-1]>self.fastMa0)      # 均线上涨
            crossBelow = (self.fastMa0<self.fastMa1 and am30.close[-1]<self.fastMa0)    # 均线下跌


            # 金叉和死叉的条件是互斥
            if (crossOver and self.trend==1 and self.wave==1):
                # 如果金叉时手头没有持仓，则直接做多
                if (self.posDict[self.symbol+"_LONG"]==0) and (self.posDict[self.symbol+"_SHORT"]==0):
                    self.buy(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                # 如果有空头持仓，则先平空，再做多
                elif self.posDict[self.symbol+"_SHORT"] == 1:
                    self.cover(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                    self.buy(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)

            # 死叉和金叉相反
            elif (crossBelow and self.trend==1 and self.wave==-1) :
                if (self.posDict[self.symbol+"_LONG"]==0) and (self.posDict[self.symbol+"_SHORT"]==0):
                    self.short(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                elif self.posDict[self.symbol+"_LONG"] == 1:
                    self.sell(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
                    self.short(self.symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
            # ---------------------------------------------------------------------

    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""

        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        #print("\n\n\n\n stg onTrade", trade.vtSymbol)
        self.transactionPrice = trade.price
        print('trade direction',trade.direction,'offset',trade.offset,'price',trade.price, trade.dt)
#         self.writeCtaLog('onTrade price:%s'%trade.price)
        # self.saveSyncData()
        pass

    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass