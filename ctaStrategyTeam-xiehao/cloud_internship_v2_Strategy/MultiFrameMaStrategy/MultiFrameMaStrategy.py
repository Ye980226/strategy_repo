from vnpy.trader.vtConstant import *
from vnpy.trader.app.ctaStrategy import CtaTemplate
import talib as ta
import numpy as np

########################################################################
# 策略继承CtaTemplate
class MultiFrameMaStrategy(CtaTemplate):
    className = 'Overshoot'
    author = 'Wang_Yue'
    
    # 策略参数
    mastop = 20
    lot = 20
    period = 72
    Shortma = 3
    Longma = 13
    
    # 策略变量
    maStop = {} # 记录趋势状态，多头1，空头-1
    transactionPrice = {} # 记录成交价格
    Stoptracking = {} #记录量是否增长
    currentvol = {}
    CurSignal = {}
    CurvolSignal = {}
    maTrend = {}
    # 参数列表，保存了参数的名称
    paramList = [
                 'mastop',
                 'period',
                 'Shortma',
                 'Longma'
                 
                ]    
    
    # 变量列表，保存了变量的名称
    varList = [
               'Stoptracking',
               'transactionPrice',
               'maStop',
               'currentvol',
               'CurSignal',
               'CurvolSignal',
               'maTrend'
              ]  
    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict', 'eveningDict']

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super().__init__(ctaEngine, setting)
    
    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略"""
        self.writeCtaLog(u'策略初始化')
        self.transactionPrice = {s:0 for s in self.symbolList}
        self.maTrend = {s:0 for s in self.symbolList}
        
        self.currentvol = {s:0 for s in self.symbolList}
        self.CurSignal = {s:0 for s in self.symbolList}
        self.CurvolSignal = {s:0 for s in self.symbolList}


        self.putEvent()

    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略"""
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
        self.onBarStopLoss(bar)

    def onBarStopLoss(self, bar):
        symbol = bar.vtSymbol
        if symbol not in self.Stoptracking.keys():
            self.Stoptracking[symbol] = 0.04
        # 计算止损止盈价位
        longStop = self.transactionPrice[symbol]*(1-self.Stoptracking[symbol])
        longProfit = self.transactionPrice[symbol]*(1+5*self.Stoptracking[symbol])
        shortStop = self.transactionPrice[symbol]*(1+self.Stoptracking[symbol])
        shortProfit = self.transactionPrice[symbol]*(1-5*self.Stoptracking[symbol])
        if symbol not in self.maStop.keys():
            self.maStop[symbol] = ""
        
        # 洗价器
        if (self.posDict[symbol+'_LONG'] > 0):
            if (bar.close < longStop):
                print('LONG stopLoss')
                self.cancelAll()
                self.sell(symbol,bar.close*0.99, self.lot)
            elif  (bar.close > longProfit or self.maStop[symbol]=="longstop"):
                print('LONG takeProfit')
                self.cancelAll()
                self.sell(symbol,bar.close*0.99, self.lot)

        elif (self.posDict[symbol+'_SHORT'] > 0):
            if (bar.close > shortStop):
                print('SHORT stopLoss')
                self.cancelAll()
                self.cover(symbol,bar.close*1.01, self.lot)
            elif (bar.close < shortProfit or self.maStop[symbol] == "shortstop"):
                print('SHORT takeProfit')
                self.cancelAll()
                self.cover(symbol,bar.close*1.01, self.lot)
        self.writeCtaLog('CurSignal:%s,maTrend:%s,CurvolSignal:%s,Stoptracking:%s,maStop:%s,longStop:%s,longProfit:%s,shortStop:%s,shortProfit:%s'
        %(self.CurSignal[symbol],self.maTrend[symbol],self.CurvolSignal[symbol],self.Stoptracking[symbol],self.maStop[symbol],longStop,longProfit,shortStop,shortProfit))
    #----------------------------------------------------------------------
    def on30MinBar(self, bar):
        """收到60MinBar推送"""
        symbol = bar.vtSymbol
        
        am15 = self.getArrayManager(symbol, "30m")
        
        if not am15.inited:
            return
        gap = (am15.close - am15.open)/am15.open
        mu = np.mean(np.abs(gap[-self.period:]))
        std = np.std(np.abs(gap[-self.period:]))
        current = gap[-1]
        volmu = np.mean(am15.volume[-self.period:])
        volstd = np.std(am15.volume[-self.period:])
        currentvol = am15.volume[-1]
        #longma = ta.EMA(am15.close,self.longperiod)
        #angel = ta.LINEARREG_ANGLE(longma,5)
        Maarr = ta.EMA(am15.close,self.mastop)
        Mashort = ta.EMA(am15.close,self.Shortma)
        Malong = ta.EMA(am15.close,self.Longma)

        if (current>0) and (current>(mu+3*std)):
            self.CurSignal[symbol] = 1
        elif (current<0) and (np.abs(current)>(mu+3*std)):
            self.CurSignal[symbol] = -1
        else:
            self.CurSignal[symbol] = 0

        if currentvol>(volmu+3*volstd):
            self.CurvolSignal[symbol] = 1
        else:
            self.CurvolSignal[symbol] = 0

        if Mashort[-1]>Malong[-1]:
            self.maTrend[symbol] = 1
        elif Mashort[-1] < Malong[-1]:
            self.maTrend[symbol] = -1
        else:
            self.maTrend[symbol] = 0

        if self.posDict[symbol+'_LONG'] > 0:
            if Mashort[-2]>Maarr[-2] and Mashort[-1]<Maarr[-1]:
                self.maStop[symbol] = "longstop"
        elif self.posDict[symbol+'_SHORT'] > 0:
            if Mashort[-2]<Maarr[-2] and Mashort[-1]>Maarr[-1]:
                self.maStop[symbol] = "shortstop"
        #volmu = sum(am15.volume[-self.period:])/self.period
        #volstd = np.std(am15.volume[-self.period:])
        #volcur = am15.volume[-1]
        #engulfing = max(am15.close[-1],am15.open[-1])>max(am15.close[-2],am15.open[-2]) and min(am15.close[-1],am15.open[-1])<min(am15.close[-2],am15.open[-2])
        if (self.CurSignal[symbol] == 1) and (self.maTrend[symbol] == 1) and (self.CurvolSignal[symbol] == 1) :
            # 做多信号
            if  (self.posDict[symbol+'_SHORT']==0)and(self.posDict[symbol+'_LONG']==0):
                self.buy(symbol, bar.close*1.01, self.lot)  # 成交价*1.01发送高价位的限价单，以最优市价买入进场
            # 如果有空头持仓，则先平空，再做多
            elif self.posDict[symbol+'_SHORT'] > 0:
                self.cancelAll() # 撤销挂单
                self.cover(symbol, bar.close*1.01, self.posDict[symbol+'_SHORT']) 
                self.buy(symbol, bar.close*1.01, self.lot)
            self.Stoptracking[symbol] = np.abs(current)*0.4
        # 做空信号
        elif (self.CurSignal[symbol] == -1) and (self.maTrend[symbol] == -1) and (self.CurvolSignal[symbol] == 1) :
            if (self.posDict[symbol+'_LONG']==0)and(self.posDict[symbol+'_SHORT']==0):
                self.short(symbol, bar.close*0.99, self.lot) # 成交价*0.99发送低价位的限价单，以最优市价卖出进场
            elif self.posDict[symbol+'_LONG'] > 0:
                self.cancelAll() # 撤销挂单
                self.sell(symbol, bar.close*0.99, self.posDict[symbol+'_LONG'])
                self.short(symbol, bar.close*0.99, self.lot)
            self.Stoptracking[symbol] = np.abs(current)*0.4
        self.putEvent()
    
    
    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass
    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        symbol = trade.vtSymbol
        if trade.offset == OFFSET_OPEN:  # 判断成交订单类型
            self.transactionPrice[symbol] = trade.price # 记录成交价格
            print(trade.tradeTime, self.posDict)
    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass