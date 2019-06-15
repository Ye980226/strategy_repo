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
class FishStrategy(CtaTemplate):
    className = 'FishStrategy'
    author = 'YJJ'
    
    # 策略交易标的的列表
    posDict = {}  # 初始化仓位字典
    eveningDict = {}
    bondDict = {}
    symbol= EMPTY_STRING
    tradeSymbol = EMPTY_STRING
    # 策略参数
    lmaPeriod = 31    #长线周期
    smaPeriod = 3     #短线周期
    cciPeriod = 16    #CCI周期
    satrWindow = 9   #STR长周期
    latrWindow = 19   #STR短周期
    fixedSize = 2     #手数
    initDays = 1      #初始化天数
    stopRatio = 0.03  #止损比例
    initbars = 40
    MA = 0
    ATR = 0
    OBV = 0
    CCI = 0
    
    # 策略变量
    transactionPrice = EMPTY_FLOAT  # 记录成交价格
    longStop = 0                        # 多头止损
    shortStop = 0                       # 空头止损
    Trend = 0
    
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'symbolList',
                 'lmaPeriod',
                 'smaPeriod',
                 'cciPeriod',
                 'satrWindow',
                 'latrWindow',
                 'initbars',
                 'fixedSize',
                 'stopRatio',
                 'initDays'
                 
                ]  
    
    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',
               'transactionPrice',
               'longStop',
               'shortStop',
               'MA',
               'OBV',
               'ATR',
               'CCI'
                    ]  
    #
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict','eveningDict','bondDict']
    

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
   # 首先找到策略的父类（就是类CtaTemplate），然后把DoubleMaStrategy的对象转换为类CtaTemplate的对象
        super(FishStrategy, self).__init__(ctaEngine, setting)
        self.OBV = 0
        self.MA30 = 0
        self.MA5 = 0
        self.CCI = 0
        self.lag = 600
        self.stopLosslong = 0
        self.stopLossshort = 0
        self.ATR = 0


        self.intraTradeHighDict = {}
        self.intraTradeLowDict = {}
    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""

        self.tradeSymbol = self.symbol = self.symbolList[0]
        # self.tradeSymbol = self.symbolList[1]

        # 构造K线合成器对象
        self.generateBarDict(self.onBar)  
        self.generateBarDict(self.onBar,60,self.on60MinBar,size =100)



        # 回测和实盘的获取历史数据部分，建议实盘初始化之后得到的历史数据和回测预加载数据交叉验证，确认代码正确
        if self.ctaEngine.engineType == 'trading':
            # 实盘载入1分钟历史数据，并采用回放计算的方式初始化策略参数
            # 通用可选参数：["1min","5min","15min","30min","60min","4hour","1day","1week","1month"]
            pastbar1 = self.loadHistoryBar(self.symbol,
                                type_ = "1min",  size = 1000)
            pastbar2 = self.loadHistoryBar(self.symbol,
                            type_ = "60min",  size = 1000)

            # 更新数据矩阵(optional)
            for bar1,bar2 in zip(pastbar1,pastbar2):    
                self.amDict[self.symbol].updateBar(bar1)    
                self.amDict[self.symbol].updateBar(bar2)
        
        elif self.ctaEngine.engineType == 'backtesting':
            # 获取回测设置中的initHours长度的历史数据
            self.initBacktesingData()    
        self.putEvent()  # putEvent 能刷新UI界面的信息

    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.mail("stg_yjj: start")
        self.putEvent()
    
    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.putEvent()

    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        # if tick.vtSymbol == self.tradeSymbol:
        #     return
        if self.ctaEngine.engineType == 'trading':
            self.bg1Dict[tick.vtSymbol].updateTick(tick)
        elif self.ctaEngine.engineType == 'backtesting':
            pass
        

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # if bar.vtSymbol == self.tradeSymbol:
        #     return
        self.bg60Dict[self.symbol].updateBar(bar)
        am = self.amDict[self.symbol]
        self.writeCtaLog('onbar,symbol:%s,time:%s,close:%s,MA:%s, OBV:%s, CCI:%s, ATR:%s'%(bar.vtSymbol,bar.datetime,bar.close,self.MA, self.OBV, self.CCI, self.ATR))
        self.putEvent()

    def on60MinBar(self, bar):
        
        # self.writeCtaLog('stg_on60Minbar_check_%s_%s_%s_%s_%s_%s_%s'%(bar.vtSymbol,bar.datetime,self.am60Dict[bar.vtSymbol].close,self.MA, self.OBV, self.CCI, self.ATR))
        self.am60Dict[bar.vtSymbol].updateBar(bar)
        am60 = self.am60Dict[self.symbol]
        
    # 洗价器------------------------------------------------------------------------------------
        if (self.posDict[self.symbol+"_LONG"] > 0):
            if (bar.close<self.transactionPrice*(1-self.stopRatio)):
                self.sell(self.symbol,bar.close*0.98,self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.stopLosslong = 1
                self.stopLong = bar.datetime
                self.writeCtaLog('平多仓 止损%s' % (bar.close))
            elif (bar.close>self.transactionPrice*(1+1.25*self.stopRatio)):
                self.sell(self.symbol,bar.close*0.98,self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('平多仓 止盈%s' % (bar.close))

        elif (self.posDict[self.symbol+"_SHORT"] > 0):
            if (bar.close>self.transactionPrice*(1+self.stopRatio)):
                self.stopLossshort = 1
                self.cover(self.symbol,bar.close*1.02,self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.stopShort = bar.datetime
                self.writeCtaLog('平空仓 止损%s' % (bar.close))
            elif (bar.close<self.transactionPrice*(1-1.25*self.stopRatio)):
                self.cover(self.symbol,bar.close*1.02,self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                self.writeCtaLog('平空仓 止盈%s' % (bar.close))
                
            self.putEvent()
        
    #止损时间控制器       
    #--------------------------------------------------------------------------------------
        if self.stopLosslong != 0:
            long = (bar.datetime - self.stopLong).total_seconds()/60
        else:
            long = self.lag+1

        if self.stopLossshort != 0:
            short = (bar.datetime - self.stopShort).total_seconds()/60
        else:
            short = self.lag+1
            
    # 指标计算   
    #---------------------------------------------------------------------------
        obv = ta.OBV(am60.close,am60.volume)
        smaobv = ta.MA(obv,self.smaPeriod)
        lmaobv = ta.MA(obv,self.lmaPeriod)
        MA30 = ta.MA(am60.close,self.lmaPeriod)
        MA5 = ta.MA(am60.close,self.smaPeriod)
        cci = ta.CCI(am60.high, am60.low, am60.close, self.cciPeriod)
        sATR = ta.ATR(am60.high, am60.low, am60.close,  self.satrWindow)
        lATR = ta.ATR(am60.high, am60.low, am60.close,  self.latrWindow)
        
    # 波动率控制
        if sATR[-1]>=1.1*lATR[-1]:
            self.ATR = 1
        elif sATR[-1]<=0.9*lATR[-1]:
            self.ATR = -1
        else:
            self.ATR = 0
        self.writeCtaLog('on60Min:time:%s,ATR:%s' % (bar.datetime,self.ATR))
    # 买卖区间控制 
        if 70<=cci[-1]<=100:
            self.CCI = 1
        elif -100<=cci[-1]<=-70:
            self.CCI = -1
        else:
            self.CCI = 0
        self.writeCtaLog('on60Min:time:%s,cci[-1]:%s' % (bar.datetime,cci[-1]))    
    # 动量信号，计算上涨下跌可能性大小
        if smaobv[-1]>=smaobv[-2] and smaobv[-1]>=lmaobv[-1]:#买入信号
            self.OBV = 1
        elif smaobv[-1]<=smaobv[-2] and smaobv[-1]<=lmaobv[-1]:#卖出信号
            self.OBV = -1
        else:
            self.OBV = 0
        self.writeCtaLog('on60Min:time:%s,smaobv[-1]:%s, smaobv[-2]:%s, lmaobv[-1]:%s' % (bar.datetime,smaobv[-1], smaobv[-2], lmaobv[-1]))    
    # 均线控制，金叉，死叉，向上向下突破
        if MA5[-1]>=MA5[-2] and MA5[-1]>=MA30[-1]:#短线穿长线
            self.MA = 1
        elif MA5[-1]<=MA5[-2] and MA5[-1]<=MA30[-1]:
            self.MA = -1
        else:
            self.MA = 0
        self.writeCtaLog('on60Min:time:%s,MA5[-1]:%s, MA5[-2]:%s, MA30[-1]:%s' % ( bar.datetime,MA5[-1], MA5[-2], MA30[-1]))      
    # 信号组合   
        Signal = self.ATR + self.CCI + self.OBV + self.MA 
      
        self.writeCtaLog('实时信号:time:%s,close:%s,MA:%s, OBV:%s, CCI:%s, ATR:%s'%(bar.datetime,bar.close,self.MA, self.OBV, self.CCI, self.ATR)) 
     
    # 进出场信号判断
        if Signal==4:
            if (self.posDict[self.tradeSymbol+"_LONG"]==0) and (self.posDict[self.tradeSymbol+"_SHORT"]==0) and long>self.lag:
                self.writeCtaLog('开多仓: symbol:%s,time:%s,close:%s,MA:%s, OBV:%s, CCI:%s, ATR:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.MA, self.OBV, self.CCI, self.ATR))
                self.buy(self.tradeSymbol,bar.close*1.02, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
            elif self.posDict[self.tradeSymbol+"_SHORT"]>0:
                self.cancelAll()
                self.cover(self.tradeSymbol,bar.close*1.02, self.posDict[self.tradeSymbol+"_SHORT"])
                if long> self.lag:
                    self.writeCtaLog('平空开多仓: symbol:%s,time:%s,close:%s,MA:%s, OBV:%s, CCI:%s, ATR:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.MA, self.OBV, self.CCI, self.ATR))
                    self.buy(self.tradeSymbol,bar.close*1.02, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                 
        elif Signal==-4:
            if (self.posDict[self.tradeSymbol+"_LONG"]==0) and (self.posDict[self.tradeSymbol+"_SHORT"]==0) and short> self.lag:
                self.writeCtaLog('开空仓: symbol:%s,time:%s,close:%s,MA:%s, OBV:%s, CCI:%s, ATR:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.MA, self.OBV, self.CCI, self.ATR))
                self.short(self.tradeSymbol,bar.close*0.98, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
            elif self.posDict[self.tradeSymbol+"_LONG"]>0:
                self.cancelAll()
                self.sell(self.tradeSymbol,bar.close*0.98, self.fixedSize)
                if short> self.lag:
                    self.writeCtaLog('平多开空仓: symbol:%s,time:%s,close:%s,MA:%s, OBV:%s, CCI:%s, ATR:%s' % (bar.vtSymbol,bar.datetime,bar.close,self.MA, self.OBV, self.CCI, self.ATR))
                    self.short(self.tradeSymbol,bar.close*0.98, self.fixedSize,priceType = PRICETYPE_MARKETPRICE, levelRate=10)
                  
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
        self.mail('stg_yjjontrade: %s,%s,%s,%s'%(trade.vtSymbol,trade.price,trade.direction,trade.offset))
    
    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass
