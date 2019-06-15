
# coding: utf-8

# In[ ]:


from __future__ import division
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta

########################################################################
# 策略继承CtaTemplate
class MultiSignalStrategy(CtaTemplate):
    className = 'MultiSignalStrategy'
    author = 'LuYiming'
    
   # 参数设置
    VWAPPeriod = 70
    BBandPeriod = 20
    roc_period = 20
    roc_ma1_period = 5;roc_ma2_period = 25
    volume_ma1_period = 5;volume_ma2_period = 25
    rsiPeriod = 10; rsiEntry = 12
    cciPeriod = 10; cciThrehold = 10
    trailingPct = 0.04
    lot = 1
    
    # 策略变量
    transactionPrice = {} # 记录成交价格
    RSI = {};CCI = {};ROC_MA = {};VWAP = {}
    breakroctrend= {}
    
    
    # 参数列表
    paramList = ['roc_period','roc_ma1_period','roc_ma2_period','trailingPct',
                'cciPeriod', 'cciThrehold',
                'trailingPct','VWAPPeriod']    
    
    # 变量列表
    varList = ['transactionPrice','intraTradeHighDict', 'intraTradeLowDict',
              'CCI', 'VWAP', 'ROC_MA','breakroctrend']  
    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        # 首先找到策略的父类（就是类CtaTemplate），然后把DoubleMaStrategy的对象转换为类CtaTemplate的对象
        super().__init__(ctaEngine, setting)
      
    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        self.transactionPrice = {s:0 for s in self.symbolList}
        self.intraTradeHighDict = {s:0 for s in self.symbolList}
        self.intraTradeLowDict = {s:999999 for s in self.symbolList}
        self.RSI = {s:0 for s in self.symbolList}
        self.VWAP = {s:0 for s in self.symbolList}
        self.ROC_MA = {s:0 for s in self.symbolList}
        self.breakroctrend={s:0 for s in self.symbolList}
        self.transactionPrice = {s:0 for s in self.symbolList} # 生成成交价格的字典
        self.putEvent()

    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略启动')
        self.putEvent()
    
    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略"""
        self.writeCtaLog(u'策略停止')
        self.putEvent()
        
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        pass
        
    #----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送"""
        symbol = bar.vtSymbol
        
        # 洗价器（止盈止损）
        if self.posDict[symbol+'_LONG'] == 0 and self.posDict[symbol+'_SHORT'] == 0:
            self.intraTradeHighDict[symbol] = 0
            self.intraTradeLowDict[symbol] = 999999

        # 持有多头仓位
        elif self.posDict[symbol+'_LONG'] >0:
            self.intraTradeHighDict[symbol] = max(self.intraTradeHighDict[symbol], bar.high)
            self.longStop = self.intraTradeHighDict[symbol]*(1-self.trailingPct)
            if bar.close<=self.longStop:
                self.cancelAll()
                self.sell(symbol, bar.close*0.9, self.posDict[symbol+'_LONG'])
            self.writeCtaLog('longStopLoss:%s'%(self.longStop))
#         # 持有空头仓位
        elif self.posDict[symbol+'_SHORT'] >0:
            self.intraTradeLowDict[symbol] = min(self.intraTradeLowDict[symbol], bar.low)
            self.shortStop = self.intraTradeLowDict[symbol]*(1+self.trailingPct)
            if bar.close>=self.shortStop:
                self.cancelAll()
                self.cover(symbol, bar.close*1.1, self.posDict[symbol+'_SHORT'])
            self.writeCtaLog('shortStopLoss:%s'%(self.shortStop))
        self.putEvent()
        
    #----------------------------------------------------------------------
    def on60minBar(self, bar):
        """收到60分钟Bar推送"""
        symbol = bar.vtSymbol
        
        am60 = self.getArrayManager(symbol, "60m") # 获取历史数组
        
        if not am60.inited:
            return
        
        # 计算策略需要的信号-------------------------------------------------
        
        ROC = ta.ROC(am60.close, self.roc_period)
        
        roc_ma1 = ta.MA(ROC, self.roc_ma1_period)
        roc_ma2 = ta.MA(ROC, self.roc_ma2_period)
        
        # 现象条件
        breakUp_roc = (roc_ma1[-1] > roc_ma2[-1]) and (roc_ma1[-2] <= roc_ma2[-2])
        breakDn_roc = (roc_ma1[-1] < roc_ma2[-1]) and (roc_ma1[-2] >= roc_ma2[-2])
        
        if (roc_ma1[-1] > roc_ma2[-1]) and (roc_ma1[-2] <= roc_ma2[-2]):
            self.breakroctrend[symbol]=1
        elif (roc_ma1[-1] < roc_ma2[-1]) and (roc_ma1[-2] >= roc_ma2[-2]):
            self.breakroctrend[symbol]=-1
        
        self.writeCtaLog('on60minBar, roc_ma1[-1]:%s, roc_ma2[-1]:%s,roc_ma1[-2]:%s,roc_ma2[-2]:%s'%(roc_ma1[-1],roc_ma2[-1],roc_ma1[-2],roc_ma2[-2]))
        # 进出场条件
        if self.breakroctrend[symbol]==1 and (self.posDict[symbol + "_LONG"]==0):
            if self.posDict[symbol + "_SHORT"] == 0:
                self.buy(symbol, bar.close * 1.01, self.lot)
            elif self.posDict[symbol + "_SHORT"] > 0:
                self.cover(symbol, bar.close * 1.01, self.posDict[symbol + "_SHORT"])
                self.buy(symbol, bar.close * 1.01, self.lot)
        elif self.breakroctrend[symbol]==-1 and (self.posDict[symbol + "_SHORT"]==0):
            if self.posDict[symbol + "_LONG"] == 0:
                self.short(symbol, bar.close * 0.9, self.lot)
            elif self.posDict[symbol + "_LONG"] > 0:
                self.sell(symbol, bar.close * 0.98, self.posDict[symbol + "_LONG"])
                self.short(symbol, bar.close *0.98, self.lot)
        
        # 发出状态更新事件
        self.putEvent()
        
    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass
    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送"""
        symbol = trade.vtSymbol
        if trade.offset == OFFSET_OPEN:  # 判断成交订单类型
            self.transactionPrice[symbol] = trade.price # 记录成交价格
    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass

