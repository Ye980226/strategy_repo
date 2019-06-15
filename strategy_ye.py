from __future__ import division
from vnpy.trader.vtConstant import EMPTY_STRING, EMPTY_FLOAT
from vnpy.trader.app.ctaStrategy.ctaTemplate import (CtaTemplate, 
                                                     BarGenerator,
                                                     ArrayManager)
# 上面提过的库

import talib as ta

########################################################################
# 策略继承CtaTemplate（策略模板）
class MinBarFishingStrategy(CtaTemplate):
    """分钟线套利策略Demo"""
    className = '分钟线套利策略'
    author = u'GenNiao'
    
    # 策略交易标的的列表
    symbolList = []         # 初始化为空
    posDict = {}  # 初始化仓位字典
    eveningDict={}
    # 多空仓位
    ALongpos = EMPTY_STRING        # 多头品种仓位
    AShortpos = EMPTY_STRING       # 空头品种仓位
    BLongpos = EMPTY_STRING        # 多头品种仓位
    BShortpos = EMPTY_STRING       # 空头品种仓位
    
    # 策略参数
    initDays = 5       # 初始化数据所用的天数
    # 启动策略时需要一些历史数据用以计算参数，一些即initDays
    
    # 策略变量
    Value = EMPTY_FLOAT #持仓成本
    
    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'symbolList',
                 'maxcost',
                 'symbolA',
                 'symbolB',
                 'LambdaA',
                 'LambdaB',
                ]    
    
    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict',#需要（同步）保存到数据库的变量
               'ev',
               'k',
               'b',
               'std'
               'spreadBuffer',
               'cost',
               'Len'
              ]  
    
    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict','eveningDict']
    

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        super(MinBarFishingStrategy, self).__init__(ctaEngine, setting)
#         self.symbolList=setting["symbolList"]
        self.LambdaA = 1
        self.LambdaB = 3
        self.k = 1
        self.b = 0
        self.std = 0
        self.spreadBuffer = []
        self.cost = 0
        self.Len = []
        
        
        
#         self.ALongpos = self.symbolA+"_LONG"
#         self.AShortpos = self.symbolA+"_SHORT"
#         self.BLongpos = self.symbolB+"_LONG"
#         self.BShortpos = self.symbolB+"_SHORT"
        
#         self.posDict[self.ALongpos]=0
#         self.posDict[self.AShortpos]=0
#         self.posDict[self.BLongpos]=0
#         self.posDict[self.BShortpos]=0
#         self.symbolList = [self.symbolA,self.symbolB]
        
        # 生成Bar数组
        self.amDict = {
            sym: ArrayManager()
            for sym in self.symbolList
        }
        
        self.am5kDict = {
            sym: ArrayManager(5000)
            for sym in self.symbolList
        }
        
    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略初始化')
        self.ctaEngine.initPosition(self)
        self.symbolA=self.symbolList[0]
        self.symbolB=self.symbolList[1]
        initData = self.loadBar(self.initDays)
        for bar in initData:
            self.onBar(bar)
        self.putEvent()

    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'策略启动')
        self.putEvent()
    
    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        print(pd.DataFrame(self.spreadBuffer))
        self.writeCtaLog(u'策略停止')
        self.putEvent()
        
    #----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        pass
        
    #----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        self.cancelAll() # 全部撤单
        symbol = bar.vtSymbol
        self.am5kDict[symbol].updateBar(bar)
        am = self.am5kDict[symbol]
        if not am.inited:
            return
        
        self.Len.append(1)
        if len(self.Len) < 5000:
            return
        
        if str(bar.datetime)[-8:-3] == '00:00': #每天更新一次
            A = self.am5kDict[self.symbolA].close[-4900:]
            B = self.am5kDict[self.symbolB].close[-4900:]
            self.k = B.dot(np.linalg.pinv([A,A*0+1]))[0]
            self.b = B.dot(np.linalg.pinv([A,A*0+1]))[1]
            # B = k*A+b
            residu = B - self.k*A -self.b
            std = np.std(residu)
            self.spreadBuffer.append([self.k,self.b,std])
            
        bd = np.std(am.close[-10:])/np.std(am.close[-100:-10])
#         if bd > 3:
#             return
        
        # 计算策略需要的信号-------------------------------------------------
        res = self.am5kDict[self.symbolB].close[-1] - (self.k * self.am5kDict[self.symbolA].close[-1] + self.b)
        res_ = self.am5kDict[self.symbolB].close[-1] - (self.k * ta.MA(self.am5kDict[self.symbolA].close[-10:],5)[-1] + self.b)
        cost = 100
        Ret = abs(res/self.am5kDict[self.symbolB].close[-1]) * 10000
            # B-A此刻价差
        
        # 构建进出场逻辑-------------------------------------------------
        if(res > (self.LambdaA * self.std) and res < res_): #价差 大于 lambda倍标准差
#         if res > 3:
            if self.posDict[self.symbolA+"_SHORT"]>0:
                self.cover(self.symbolA,99999,self.posDict[self.symbolA+"_SHORT"])
            if self.posDict[self.symbolB+"_LONG"]>0:
                self.sell(self.symbolB,1,self.posDict[self.symbolB+"_LONG"])
        if(res > (self.LambdaB * self.std) and res < res_ and Ret > cost and self.posDict[self.symbolA+"_LONG"]==0):
#         if(res > 10):
            self.buy(self.symbolA,99999,10000/self.am5kDict[self.symbolA].close[-1])
            self.short(self.symbolB,1,10000/self.am5kDict[self.symbolB].close[-1])
            pass
        
        if(res < (self.LambdaA * self.std) and res > res_): #价差 小于 lambda倍标准差
#         if(res < 3):
            if self.posDict[self.symbolB+"_SHORT"]>0:
                self.cover(self.symbolB,99999,self.posDict[self.symbolB+"_SHORT"])
            if self.posDict[self.symbolA+"_LONG"]>0:
                self.sell(self.symbolA,1,self.posDict[self.symbolA+"_LONG"])
        if(res < (self.LambdaB * self.std) and res > res_ and Ret > cost and self.posDict[self.symbolA+"_SHORT"]==0):    
#         if(res < 10):
            self.buy(self.symbolB,99999,10000/self.am5kDict[self.symbolB].close[-1])
            self.short(self.symbolA,1,10000/self.am5kDict[self.symbolA].close[-1])
            pass
        
        self.putEvent()
        
    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass
    
    #----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        pass
    
    #----------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        print('停止单推送')
        pass
from vnpy.trader.app.ctaStrategy.ctaBacktesting import BacktestingEngine, OptimizationSetting, MINUTE_DB_NAME
import numpy as np
import pandas as pd
import talib as tb
# BacktestingEngine 是一个引擎整体包，用以创建引擎
# 此处的代码是创建一个BacktestingEngine对象然后修改对象的参数
# 初始化

# 创建回测引擎对象
engine = BacktestingEngine()
# 设置回测使用的数据
engine.setBacktestingMode(engine.BAR_MODE)    # 设置引擎的回测模式为K线
# barMODE的意思是每根线进来（每分钟一次）刷新一次策略
# tick与之对应，每个数据进来刷新一次
# 通常用barMode


engine.setDatabase('VnTrader_1Min_Db')  # 设置使用的历史数据库
# 数据库中有两个库，一个叫VnTrader——分钟数据库
# 另一个是VnTrade——tick数据库
# 数据库与MODE对应

engine.setStartDate('20180106 00:00',initHours=5*24)               # 设置回测用的数据起始日期
engine.setEndDate('20180809 00:00')
# 配置回测引擎参数
# 为了让回测结果更接近真实情况
engine.setSlippage(0.2)     # 设置滑点为股指1跳 
#信号时出现的价格未必能成功买入，需要承受一定价差，称为滑点
engine.setRate(1/2000)   # 设置手续费千1
engine.setSize(1)         # 设置合约大小
engine.setPriceTick(0.1)    # 设置股指最小价格变动   
engine.setCapital(50000)  # 设置回测本金
d = {
    'symbolList':['BTCUSDT:binance','ETHUSDT:binance']
}                    # 策略参数配置
engine.initStrategy(MinBarFishingStrategy, d)    # 创建策略对象
engine.runBacktesting() #运行策略
for i in range(10):
    d = engine.tradeDict[str(i+1)].__dict__
    print('TradeID: %s, Time: %s, Direction: %s, Price: %s, Volume: %s' %(d['tradeID'], d['dt'], d['direction'], d['price'], d['volume']))
# 显示逐日回测结果
engine.showDailyResult()
# 显示逐笔回测结果
engine.showBacktestingResult()