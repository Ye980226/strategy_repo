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


class multiATR_Strategy(CtaTemplate):
    className = 'multiATR_Strategy'
    author = 'Sky'
    
    # 策略交易标的
    symbol = EMPTY_STRING  
    posDict = {}  # 仓位数据缓存
    eveningDict = {}  # 可平仓量数据缓存
    bondDict = {}  # 保证金数据缓存
    up_value = 16
    down_value = 16
    window1 = 18
    window2 = 28
    trailingPercent = 4
    fixsize = 1

    stopRatio = 0.02       # 止损百分比
    profitMultiplier = 6   # 止盈与止损比例
    transactionPrice = {}  # 记录成交价格
    intraTradeHighDict = {}
    intraTradeLowDict = {}
    adx_con = {}  # 均线趋势，多头1，空头-1
    atr_con = {}
    cross = {}
    Ma_exit = {}
    MA_CON = {}
    # 策略变量
    initbars = 100  # 获取历史数据的条数
    
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
                'profitMultiplier',
                'downband',
                'upband']   

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
        self.adx_con = {s: 0 for s in self.symbolList}
        self.atr_con = {s: 0 for s in self.symbolList}
        self.cross = {s: 0 for s in self.symbolList}
        self.transactionPrice = {s: 0 for s in self.symbolList}
        self.Ma_exit = {s: 0 for s in self.symbolList}
        self.MA_CON = {s: 0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict ={s: 0 for s in self.symbolList} 
        
        self.generateBarDict(self.onBar)  
        self.generateBarDict(self.onBar,15,self.on15MinBar,size =100)
        self.generateBarDict(self.onBar,30,self.on30MinBar,size =100)
        if self.ctaEngine.engineType == 'trading':
            pastBarDict = {s+"1min" : self.loadHistoryBar(s,type_ = "1min",  size = 1200) for s in self.symbolList}
            pastBar15Dict = {s+"30min" : self.loadHistoryBar(s,type_ = "30min",  size = 1000)[:-20] for s in self.symbolList}
            bar30Dict = {s: pastBar30Dict[s+'30min'] for s in self.symbolList}
            for s in self.symbolList:
                for bar in bar30Dict[s]:
                    self.am30Dict[s].updateBar(bar)

            barDict = {s: pastBarDict[s+'1min'] for s in self.symbolList}
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
        self.writeCtaLog('stg_onbar_check_%s_%s_%s'%(bar.vtSymbol,bar.datetime,bar.close))
        
        self.bg15Dict[bar.vtSymbol].updateBar(bar)
        self.bg30Dict[bar.vtSymbol].updateBar(bar)
        am = self.amDict[symbol]
        
        # 持有多头仓位
        if self.posDict[symbol+"_LONG"] == 0 and self.posDict[symbol+"_SHORT"] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999
        # 洗价器
        elif (self.posDict[symbol+"_LONG"] > 0):
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.intraTradeLowDict[symbol] = bar.low
            self.longStop = self.intraTradeHighDict[symbol]*(1-self.trailingPercent/100)
#             print('最高价:%s'%self.intraTradeHighDict[symbol])
#             print('止损价格:%s'%self.longStop)
#             print('开仓价格:%s'%self.transactionPrice)
            if bar.close<=self.longStop or (bar.close > self.transactionPrice[symbol] * (1 + self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.sell(symbol, bar.close*0.98, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
#                 self.writeCtaLog('平多仓 止盈或止损')
        elif (self.posDict[symbol+"_SHORT"] > 0):
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.intraTradeHighDict[symbol] = bar.high
            self.shortStop = self.intraTradeLowDict[symbol]*(1+self.trailingPercent/100)
            if (bar.close>=self.shortStop) or (bar.close < self.transactionPrice[symbol] * (1 - self.profitMultiplier * self.stopRatio)):
                self.cancelAll()
                self.cover(symbol, bar.close*1.02, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 10)
            
        self.putEvent()

        # ----------------------------------------------------------------------
    def on15MinBar(self, bar):
            """60分钟K线推送"""
            symbol = bar.vtSymbol
            self.am15Dict[bar.vtSymbol].updateBar(bar)
        
            am15 = self.am15Dict[symbol]


            
            atr20 = ta.ATR(am15.high,am15.low,am15.close,14)
            
            atr50 = ta.ATR(am15.high,am15.low,am15.close,66)
            
            self.upband = ta.MAX(am15.close,self.up_value)
            
            self.downband = ta.MIN(am15.close,self.down_value)
            
            if am15.close[-2]<self.upband[-2] and am15.close[-1]>self.upband[-2]:
                self.cross[symbol] = 1
            elif am15.close[-2]>self.downband[-2] and am15.close[-1]<self.downband[-2]:
                self.cross[symbol] = -1
            else:
                self.cross[symbol] = 0
                
                
            if atr20[-1]>atr50[-1]:
                self.atr_con[symbol] = 1
            else:
                self.atr_con[symbol] = 0
                
             
           
    def on30MinBar(self, bar):
            """60分钟K线推送"""
            symbol = bar.vtSymbol
            self.am30Dict[bar.vtSymbol].updateBar(bar)
        
            am30 = self.am30Dict[symbol]
            
            MA6 = ta.MA(am30.close,self.window1)
            
            MA22 = ta.MA(am30.close,self.window2)
            self.Ma_exit[symbol] = MA22[-1]
            
            adx = ta.ADX(am30.high,am30.low,am30.close,14)

                
            if adx[-1]>33:
                self.adx_con[symbol] = 1
            else:
                self.adx_con[symbol] = 0
                
                
             
            ####              把均线做一个加和求出一段时间的MA是大于的，避免假信号，可以不用多，两三天。
            if MA6[-1]>MA6[-2] and MA22[-1]>MA22[-2]:
                self.MA_CON[symbol] = 1
            elif MA6[-1]<MA6[-2] and MA22[-1]<MA22[-2]:
                self.MA_CON[symbol] = -1
            else:
                self.MA_CON[symbol] = 0
                
            #print('cross:%s,adx:%s,atr:%s,MACON:%s'%(self.cross[symbol],self.adx_con[symbol],self.atr_con[symbol],self.MA_CON[symbol]))
            # 金叉和死叉的条件是互斥
            if (self.cross[symbol] == 1 and self.adx_con[symbol] == 1 and self.atr_con[symbol] == 1 and self.MA_CON[symbol] == 1):
                # 如果金叉时手头没有持仓，则直接做多
                if (self.posDict[symbol+"_LONG"]==0) and (self.posDict[symbol+"_SHORT"]==0):
                    self.buy(symbol,bar.close*1.015, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 20)
                # 如果有空头持仓，则先平空，再做多
                elif self.posDict[symbol+"_SHORT"] == 1:
                    self.cover(symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 20)
                    self.buy(symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 20)

            # 死叉和金叉相反
            elif (self.cross[symbol] == -1 and self.adx_con[symbol] == 1 and self.atr_con[symbol] == 1 and self.MA_CON[symbol] == -1) :
                if (self.posDict[symbol+"_LONG"]==0) and (self.posDict[symbol+"_SHORT"]==0):
                    self.short(symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 20)
                elif self.posDict[symbol+"_LONG"] == 1:
                    self.sell(symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 20)
                    self.short(symbol,bar.close, self.fixsize,priceType=PRICETYPE_LIMITPRICE,levelRate = 20)
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""

        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        symbol = trade.vtSymbol
        #print("\n\n\n\n stg onTrade", trade.vtSymbol)
        self.transactionPrice[symbol] = trade.price
        #print('trade direction',trade.direction,'offset',trade.offset,'price',trade.price, trade.dt)
#         self.writeCtaLog('onTrade price:%s'%trade.price)
        # self.saveSyncData()
        pass

    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass