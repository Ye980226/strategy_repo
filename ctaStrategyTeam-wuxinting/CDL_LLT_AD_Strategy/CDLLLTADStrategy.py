
# coding: utf-8

# In[5]:

from __future__ import division
from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
import numpy as np
import copy
########################################################################
# 策略继承CtaTemplate
class CDLLLTADStrategy(CtaTemplate):
    """蜡烛图均线策略Demo"""
    className = 'CDLLLTADStrategy'
    author = 'Qiudaokai'
    
    # 策略参数
    fastPeriod = 30   #均线短周期 
    slowPeriod = 60   #均线长周期
    fastADperiod = 10 #AD均线短周期
    slowADperiod = 80 #AD均线长周期
    stopLossPct = 0.03 #止损参数
    takeProfitPct = 0.08  #止盈参数
    lot = 1            # 设置手数
    # 策略变量
    transactionPrice = {} # 记录成交价格
    maTrend = {} # 记录趋势状态，多头1，空头-1
    # 参数列表
    paramList = ['fastPeriod',
                 'slowPeriod',
                'stopLossPct',
                'takeProfitPct',
                'fastADperiod',
                'slowADperiod']    
    
    # 变量列表
    varList = ['transactionPrice',
               'maTrend',
                'intraTradeHighDict',
              'intraTradeLowDict']   
    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        # 首先找到策略的父类（就是类CtaTemplate），然后把CDL_LLT_ADStrategy的对象转换为类CtaTemplate的对象
        super().__init__(ctaEngine, setting)
      
    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        self.transactionPrice = {s:0 for s in self.symbolList} # 生成成交价格的字典
        self.maTrend = {s:0 for s in self.symbolList}
        self.intraTradeHighDict = {s: 0 for s in self.symbolList}
        self.intraTradeLowDict = {s: 999999 for s in self.symbolList}
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
        self.onBarStopLoss(bar)
        
    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol
       # 计算止损止盈价位
        longStop = self.transactionPrice[symbol]*(1-self.stopLossPct)
        longProfit = self.transactionPrice[symbol]*(1+3*self.takeProfitPct)
        shortStop = self.transactionPrice[symbol]*(1+self.stopLossPct)
        shortProfit = self.transactionPrice[symbol]*(1-3*self.takeProfitPct)

        # 洗价器
        if (self.posDict[symbol+'_LONG'] > 0):
            if (bar.close < longStop):
                self.writeCtaLog('longStopLoss:%s'%(longStop))
                self.cancelAll()
                self.sell(symbol,bar.close*0.98, self.posDict[symbol+'_LONG'])
            elif  (bar.close > longProfit):
                self.writeCtaLog('longProfit:%s'%(longProfit))
                self.cancelAll()
                self.sell(symbol,bar.close*0.98, self.posDict[symbol+'_LONG'])

        elif (self.posDict[symbol+'_SHORT'] > 0):
            if (bar.close > shortStop):
                self.writeCtaLog('shortStopLoss:%s'%(shortStop))
                self.cancelAll()
                self.cover(symbol,bar.close*1.02, self.posDict[symbol+'_SHORT'])
            elif (bar.close < shortProfit):
                self.writeCtaLog('shortProfit:%s'%(shortProfit))
                self.cancelAll()
                self.cover(symbol,bar.close*1.02, self.posDict[symbol+'_SHORT'])
        
    #----------------------------------------------------------------------
    def LLT(self,closePrice,per):          #低延迟趋势线，经测试比MA/EMA更适合结合蜡烛图判断趋势
        close=copy.deepcopy(closePrice)       #深复制，原始对象的改变不会造成深拷贝里任何子元素的改变
        llt=copy.deepcopy(closePrice)
        mul=2.0/(per+1.0)
        for i in np.arange(2,len(llt)):    #从3开始，前两个用close赋值
            llt[i]=(mul-(mul*mul)/4)*close[i]+((mul*mul)/2)*close[i-1]-(mul-3*(mul*mul)/4)*close[i-2]+2*(1-mul)*llt[i-1]-(1-mul)*(1-mul)*llt[i-2]
        return llt
    
    #----------------------------------------------------------------------
    def on60MinBar(self, bar):
        """收到60MinBar推送"""
        symbol = bar.vtSymbol
        
        am60 = self.getArrayManager(symbol, "60m")
        
        if not am60.inited:
            return
        
        fastMa = self.LLT(am60.close, self.fastPeriod)
        slowMa = self.LLT(am60.close, self.slowPeriod)

        fastAD = self.LLT(ta.AD(am60.high, am60.low, am60.close, am60.volume), self.fastADperiod)
        slowAD = self.LLT(ta.AD(am60.high, am60.low, am60.close, am60.volume), self.slowADperiod)
        #长短期均线及AD判断趋势
        if fastMa[-1] > slowMa[-1] and fastAD[-1] > slowAD[-1]:
            self.maTrend[symbol] = 1
        elif fastMa[-1] < slowMa[-1] and fastAD[-1] < slowAD[-1]:
            self.maTrend[symbol] = -1
        self.writeCtaLog('on60minBar, fastMa[-1]:%s, slowMa[-1]:%s,fastAD[-1]:%s,slowAD[-1]:%s'%(fastMa[-1],slowMa[-1],fastAD[-1],slowAD[-1]))            
    #----------------------------------------------------------------------
    def on15MinBar(self, bar):
        """收到15MinBar推送"""
        symbol = bar.vtSymbol
        
        am15 = self.getArrayManager(symbol, "15m")
 
        if not am15.inited:
            return
        
        hangingman = ta.CDLHANGINGMAN(am15.open, am15.high, am15.low, am15.close)
        invertedhammer = ta.CDLINVERTEDHAMMER(am15.open, am15.high, am15.low, am15.close)
        self.writeCtaLog('invertedhammer[-1]:%s, hangingman[-1]:%s,self.maTrend:%s'%(invertedhammer[-1],hangingman[-1],self.maTrend[symbol]))
        # invertedhammer发出信号， 趋势为多头， 多头没有持仓
        if invertedhammer[-1] == 100 and self.maTrend[symbol] == 1 and (self.posDict[symbol+'_LONG']==0):
            if  (self.posDict[symbol+'_SHORT']==0):
                self.buy(symbol, bar.close*1.01, self.lot)  # 成交价*1.01发送高价位的限价单，以最优市价买入进场
            elif (self.posDict[symbol+'_SHORT'] > 0):
                self.cancelAll() # 撤销挂单
                self.cover(symbol, bar.close*1.01, self.posDict[symbol+'_SHORT']) 
                self.buy(symbol, bar.close*1.01, self.lot)
        
        # hangingman发出信号， 趋势为空头， 空头没有持仓
        if hangingman[-1] == -100 and self.maTrend[symbol] == -1 and (self.posDict[symbol+'_SHORT']==0):
            if (self.posDict[symbol+'_LONG']==0):
                self.short(symbol, bar.close*0.99, self.lot) # 成交价*0.99发送低价位的限价单，以最优市价卖出进场
            elif (self.posDict[symbol+'_LONG'] > 0):
                self.cancelAll() # 撤销挂单
                self.sell(symbol, bar.close*0.99, self.posDict[symbol+'_LONG'])
                self.short(symbol, bar.close*0.99, self.lot)
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