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
class MultiSignalHYStrategy(CtaTemplate):
    className = 'MultiSignalHYStrategy'
    author = 'hy'
    
    # 策略交易标的的列表
    symbol = EMPTY_STRING      # 初始化

    
    tradeList = []
    posDict = {}  # 仓位数据缓存
    eveningDict = {}  # 可平仓量数据缓存
    bondDict = {}  # 保证金数据缓存
    

    initDays = 1
    # 策略参数
    amWindow = 19
    smaPeriod = 16
    lmaPeriod = 21
    svolmaPeriod=3
    lvolmaPeriod=19
    threshold = 2
    stopRatio = 0.02  # 止损比例
 
   
    # 策略变量
    transactionPrice = EMPTY_FLOAT # 记录成交价格
    fixedSize = 10
    longStop = EMPTY_FLOAT
    shortStop = EMPTY_FLOAT
    
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'symbolList',
                 'amWindow',
                 'svolmaPeriod',
                 'lvolmaPeriod',
                 'smaPeriod',
                 'lmaPeriod',
                 'threshold',
                  'stopRatio']  
    
    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'transactionPrice',
               'fixedSize',
               'longStop',
               'shortStop']  
    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict','eveningDict','bondDict']

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        
        # 首先找到策略的父类（就是类CtaTemplate），然后把DoubleMaStrategy的对象转换为类CtaTemplate的对象
        super(MultiSignalHYStrategy, self).__init__(ctaEngine, setting)
        
        self.intraTradeHighDict = {}
        self.intraTradeLowDict = {}
        self.OBV = 0
        self.Vol = 0
        self.MA = 0
    
    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""

        self.symbol = self.symbolList[0]
        # self.symbol = self.symbolList[1]

       # 提供了generateBarDict，自动生成bgDick与amDict
        self.generateBarDict(self.onBar, 60, self.on60MinBar,size =100)
        self.generateBarDict(self.onBar, 30, self.on30MinBar, size =100)
        self.generateBarDict(self.onBar)



        # 回测和实盘的获取历史数据部分，建议实盘初始化之后得到的历史数据和回测预加载数据交叉验证，确认代码正确
        if self.ctaEngine.engineType == 'trading':
            # 实盘载入1分钟历史数据，并采用回放计算的方式初始化策略参数
            # 通用可选参数：["1min","5min","15min","30min","60min","4hour","1day","1week","1month"]
            pastbar1 = self.loadHistoryBar(self.symbol,
                                type_ = "1min",  size = 1000)
            pastbar2 = self.loadHistoryBar(self.symbol,
                            type_ = "60min",  size = 1000)
            pastbar3 = self.loadHistoryBar(self.symbol,
                            type_ = "30min",  size = 1000)

            # 更新数据矩阵(optional)
            for bar1,bar2,bar3 in zip(pastbar1,pastbar2,pastbar3):    
                self.amDict[self.symbol].updateBar(bar1)    
                self.amDict[self.symbol].updateBar(bar2)
                self.amDict[self.symbol].updateBar(bar3)
            
            self.transactionPrice =pastbar1[-1].close
        elif self.ctaEngine.engineType == 'backtesting':
            # 获取回测设置中的initHours长度的历史数据
            self.initBacktesingData()    
        self.putEvent()  # putEvent 能刷新UI界面的信息
    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.mail("stg_hy: start")
        self.putEvent()
    
    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.putEvent()
        
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        # if tick.vtSymbol == self.symbol:
        #     return
        if self.ctaEngine.engineType == 'trading':
            self.bg1Dict[tick.vtSymbol].updateTick(tick)
        elif self.ctaEngine.engineType == 'backtesting':
            pass
        
    #----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # if bar.vtSymbol == self.symbol:
        #     return

        self.bg60Dict[self.symbol].updateBar(bar)
        self.bg30Dict[self.symbol].updateBar(bar)
        am = self.amDict[self.symbol]


        self.writeCtaLog(' stg_onBar: time:%s,symbol:%s,close:%s, obv:%s,ma:%s, vol:%s'%(bar.datetime,bar.vtSymbol,bar.close, self.OBV, self.MA,self.Vol))
    
        # 洗价器，就是止损
        if (self.posDict[self.symbol+"_LONG"] > 0):
            if (bar.close<self.transactionPrice*(1-self.stopRatio)) :
                self.sell(self.symbol,bar.close*0.98, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('平多仓 止损%s' % (bar.close))
            elif (bar.close > self.transactionPrice * (1 + 3 * self.stopRatio)):
                self.sell(self.symbol, bar.close * 0.98, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('平多仓 止盈%s' % (bar.close))
        elif (self.posDict[self.symbol+"_SHORT"] > 0):
            if (bar.close>self.transactionPrice*(1+self.stopRatio)) :
                self.cover(self.symbol,bar.close*1.02, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('平空仓 止损%s' % (bar.close))
            elif (bar.close < self.transactionPrice * (1 - 3 * self.stopRatio)):
                self.cover(self.symbol, bar.close * 1.02, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('平空仓 止盈%s' % (bar.close))

    def on30MinBar(self, bar):
   
        self.am30Dict[self.symbol].updateBar(bar)
        am30 = self.am30Dict[self.symbol]
        if not am30.inited:
            return
        #OBV
        #obv = ta.OBV(am30.close,am30.volume)
        obv =ta.AD(am30.high,am30.low,am30.close,am30.volume)
        self.writeCtaLog('%s AD:%s'%(bar.datetime,obv))

        if obv[-1]>obv[-2] and am30.close[-1]<am30.close[-2]:
            self.OBV = 1
        elif obv[-1]<obv[-2] and am30.close[-1]>am30.close[-2]:
            self.OBV = -1
        else:
            self.OBV = 0
        
        # 发出状态更新事件
        self.putEvent()

    def on60MinBar(self, bar):
        
        self.am60Dict[self.symbol].updateBar(bar)
        am60 = self.am60Dict[self.symbol]
        if not am60.inited:
            return
        #成交量与均线的思想结合
        VolSMA5 = ta.MA(am60.volume, self.svolmaPeriod)
        VolSMA20 = ta.MA(am60.volume, self.lvolmaPeriod)
        VolSMA=(VolSMA5+VolSMA20)/2
        
        self.writeCtaLog('%s Vol:%s, VolSMA[-2]:%s'%(bar.datetime,am60.volume[-2], VolSMA[-2]))
        if am60.volume[-2]>VolSMA[-2]:
            self.Vol = 1
        elif am60.volume[-2]<VolSMA[-2]:
            self.Vol = -1
        else:
            self.Vol = 0
            
        MA15 = ta.MA(am60.close, self.smaPeriod)
        MA20 = ta.MA(am60.close, self.lmaPeriod)
      #  print(MA5)
        self.writeCtaLog('MA15[-2]:%s, MA20[-2]:%s'%(MA15[-2], MA20[-2]))
        if MA15[-2]>MA20[-2]:
            self.MA = 1
        elif MA15[-2]<MA20[-2]:
            self.MA = -1
        else:
            self.MA = 0
        
        Signal = self.MA+self.OBV+self.Vol
        self.writeCtaLog(' 实时信号: time:%s,symbol:%s,close:%s, obv:%s,ma:%s, vol:%s'%(bar.datetime,bar.vtSymbol,bar.close, self.OBV, self.MA,self.Vol))

        if Signal>=2:
            if (self.posDict[self.symbol+"_LONG"]==0) and (self.posDict[self.symbol+"_SHORT"]==0):
                self.writeCtaLog('开多实时信号: time:%s,symbol:%s,close:%s, obv:%s,ma:%s, vol:%s'%(bar.datetime,bar.vtSymbol,bar.close, self.OBV, self.MA,self.Vol))
                self.buy(self.symbol,bar.close*1.02, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
            elif self.posDict[self.symbol+"_SHORT"] > 0:
                self.cancelAll()
                self.cover(self.symbol,bar.close*1.02, self.posDict[self.symbol+"_SHORT"])
                self.writeCtaLog('平空开多实时信号: time:%s,symbol:%s,close:%s, obv:%s,ma:%s, vol:%s'%(bar.datetime,bar.vtSymbol,bar.close, self.OBV, self.MA,self.Vol))
                self.buy(self.symbol,bar.close*1.02, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('discover a buy signal')
            
        elif Signal<=-2:
            if (self.posDict[self.symbol+"_LONG"]==0) and (self.posDict[self.symbol+"_SHORT"]==0):
                self.writeCtaLog('开空实时信号: time:%s,symbol:%s,close:%s, obv:%s,ma:%s, vol:%s'%(bar.datetime,bar.vtSymbol,bar.close, self.OBV, self.MA,self.Vol))
                self.short(self.symbol,bar.close*0.98, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
            elif self.posDict[self.symbol+"_LONG"]>0:
                self.cancelAll()
                self.sell(self.symbol,bar.close*0.98, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('平多开空实时信号: time:%s,symbol:%s,close:%s, obv:%s,ma:%s, vol:%s'%(bar.datetime,bar.vtSymbol,bar.close, self.OBV, self.MA,self.Vol))
                self.short(self.symbol,bar.close*0.98, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('discover a short signal')
        self.putEvent()

    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass
    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        self.transactionPrice = trade.price
        self.writeCtaLog('onTrade price:%s' % trade.price)
        self.mail('stg_ontrade: %s,%s,%s,%s'%(trade.vtSymbol,trade.price,trade.direction,trade.offset))

    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass