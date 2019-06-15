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

class Strategy_HighFrequency(CtaTemplate):
    
    className = 'StrategyHighFrequency'      #策略和仓位数据表的名称
    author = 'Leon'

    # 策略交易标的
    activeSymbol = ""     # 主动品种
    passiveSymbol = ""    # 被动品种

    posDict = {}                    # 仓位数据缓存
    eveningDict = {}                # 可平仓量数据缓存
    bondDict = {}                   # 保证金数据缓存

    # 策略变量
    posSize = 1                     # 每笔下单的数量
    initbars = 100                  # 获取历史数据的条数 
    flag = 0

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'activeSymbol',
                 'passiveSymbol'
                 ]

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'posDict'
               ]

    # 同步列表，保存了需要保存到数据库的变量名称
    syncList = ['posDict',
                'eveningDict',
                'bondDict']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(Strategy_HighFrequency, self).__init__(ctaEngine, setting)
             
    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.activeSymbol = self.symbolList[0]    # 主动品种
        # self.passiveSymbol = self.symbolList[1]   # 被动品种
        self.pos=0
        # 构造K线合成器对象
        self.bgDict = {
            sym: BarGenerator(self.onBar)
            for sym in self.symbolList
        }
        self.bg30Dict={
            sym: BarGenerator(self.onBar,30,self.on30MinBar)
            for sym in self.symbolList
        }
        self.amDict = {
            sym: ArrayManager(size=60*2+1)
            for sym in self.symbolList
        }
        self.am30Dict={
            sym:ArrayManager()#self.am10Dict[self.activeSymbol].updateBar(bar)会更新k线，ArrayManager默认size是100，就是缓存一个100个的数组的open，high，low，close数据
            for sym in self.symbolList
        }

        self.hfDict = {sym: BarGenerator(self.onhfBar,xSecond = 10)
            for sym in self.symbolList
        }
        
        # self.hfDict = {
        #     sym: ArrayManager()
        #     for sym in self.symbolList
        # }

        # 载入1分钟历史数据，并采用回放计算的方式初始化策略参数
        # 可选参数：["1min","5min","15min","30min","60min","4hour","1day","1week","1month"]
        # pastbar1 = self.loadHistoryBar(self.activeSymbol,
        #                     type_ = "1min", 
        #                     size = self.initbars)

        # pastbar2 = self.loadHistoryBar(self.passiveSymbol,
        #                 type_ = "1min", 
        #                 size = self.initbars)
        
        # for bar1,bar2 in zip(pastbar1,pastbar2):    
        #     self.amDict[self.activeSymbol].updateBar(bar1)    # 更新数据矩阵(optional)
        #     self.amDict[self.passiveSymbol].updateBar(bar2)

        # self.onBar(bar)  # 是否直接推送到onBar
        self.enter_long=False
        self.enter_short=False
        self.out_sell=False
        self.out_cover=False
        self.Indicator=0
        self.opentime=0
        self.kShortestPaths=list()
        self.putEvent()  # putEvent 能刷新UI界面的信息
        '''
        在点击初始化策略时触发,载入历史数据,会推送到onbar去执行updatebar,但此时ctaEngine下单逻辑为False,不会触发下单.
        '''
    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.putEvent()
        '''
        在点击启动策略时触发,此时的ctaEngine会将下单逻辑改为True,此时开始推送到onbar的数据会触发下单.
        '''
    # ----------------------------------------------------------------------
    
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.putEvent()
        
    # ----------------------------------------------------------------------
    def onRestore(self):
        """从错误状态恢复策略（必须由用户继承实现）"""
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送"""
        self.bgDict[tick.vtSymbol].updateTick(tick)
    
    
        '''
        在每个Tick推送过来的时候,进行updateTick,生成分钟线后推送到onBar. 
        注：如果没有updateTick，将不会推送分钟bar
        '''
    # ----------------------------------------------------------------------
    def onBar(self,bar):
        """收到1分钟K线推送"""
        # self.bg30Dict[bar.vtSymbol].updateBar(bar)
        
        self.amDict[bar.vtSymbol].updateBar(bar)
        if not self.amDict[bar.vtSymbol].inited:
            return
        
        openArray=np.array(self.amDict[bar.vtSymbol].openArray)[-30:]
        # print(openArray)

        closeArray=np.array(self.amDict[bar.vtSymbol].closeArray)[-31:]
        # volume=self.amDict[bar.vtSymbol].volume
        rateArray=(closeArray[1:]-closeArray[-1:])/closeArray[-1:]

        highArray=np.array(self.amDict[bar.vtSymbol].highArray)[-30:]
        lowArray=np.array(self.amDict[bar.vtSymbol].lowArray)[-30:]
        volume=np.array(self.amDict[bar.vtSymbol].volumeArray)[-30:]
        
        # print(np.abs(closeArray-openArray))
        K_shortest_path=np.sum(np.abs(closeArray[-30:]-openArray)+np.abs(highArray-lowArray)+np.abs(highArray-closeArray[-30:]))/np.sum(volume)
        
        # print(K_shortest_path)
        self.kShortestPaths.append(K_shortest_path)
        rateMean=np.mean(np.abs(rateArray[:-1]))
        shortATR=ta.ATR(highArray,lowArray,closeArray[-30:],1)
        longATR=ta.ATR(highArray,lowArray,closeArray[-30:],29)

        if len(self.kShortestPaths)<30:
            return 
        if len(self.kShortestPaths)%10==0:
            self.longMeanKShortIndicator=np.mean(self.kShortestPaths[-30:])
            kShortestPaths=np.array(self.kShortestPaths[-30:])
            self.slope=np.cov(kShortestPaths,rateArray)[0,1]/np.var(np.abs(rateArray))
            self.alpha=np.mean(kShortestPaths)-self.slope*np.mean(np.abs(rateArray))
        
        
         
        # print("%f : %f"%(self.kShortestPaths[-1],self.longMeanKShortIndicator))
        # print("rateArray",rateArray)
        # print("longATR",longATR)
        # print("shortATR[-1]:%f"%shortATR[-1])
        # print("longATR[-1]:%f"%longATR[-1])
        # print("rateArray[-1]:%f"%rateArray[-1])
        if self.kShortestPaths[-1]<self.slope*rateArray[-1]+self.alpha and rateArray[-1]>3*rateMean and shortATR[-1]>2*longATR[-1]:
            self.enter_short=True
        else:
            self.enter_short=False
        # if self.kShortestPaths[-1]<0.25*self.longMeanKShortIndicator:
            # self.enter_long=True
        # else:
            # self.enter_long=False

    
        # self.out=True
        # print("self.out",self.out)
        
        
        if self.pos==0 and  self.enter_short:
            self.buy(bar.vtSymbol,99999,1)
            print("空头进场")
            # self.enter_short=False
            # self.out=True
            # self.Indicator=self.longMeanKShortIndicator
            self.pos=1
        # if self.pos==0  and self.enter_long:
        #     self.buy(bar.vtSymbol,99999,1)
        #     print("多头进场")
        #     # self.enter_long=False
        #     # self.out=True
        #     self.Indicator=self.longMeanKShortIndicator
        #     self.pos=-1
        
        # if self.Indicator and (self.posDict[bar.vtSymbol+"_LONG"]>0 or self.posDict[bar.vtSymbol+"_SHORT"]>0):
        #     if self.kShortestPaths[-1]>self.Indicator:
        #         self.out_sell=True
        #     else:
        #         self.out_sell=False
        #     if self.kShortestPaths[-1]<self.Indicator:
        #         self.out_cover=True
        #     else:
        #         self.out_cover=False
        if (self.posDict[bar.vtSymbol+"_LONG"]>0 or self.posDict[bar.vtSymbol+"_SHORT"]>0):

            if self.pos==1 and (bar.datetime-self.opentime).total_seconds()>=15*60:   
                self.sell(bar.vtSymbol,1,1)
                print("空头平仓")
                self.pos=0
                self.Indicator=0
                self.out_cover=False
        # if self.pos==-1 and self.out_sell:
        #     self.sell(bar.vtSymbol,1,1)
        #     print("多头平仓")
        #     self.pos=0
        #     self.Indicator=0
        #     self.out_sell=False   
        
        if len(self.kShortestPaths)%240==0:
            del self.kShortestPaths[:-120]

    def on30MinBar(self,bar):
        # self.amDict[bar.vtSymbol].updateBar(bar)
        
        self.putEvent()
        pass

    def onhfBar(self,bar):
        self.writeCtaLog("%s, %s,444444444444444444,%s"%(bar.datetime,bar.vtSymbol,bar.close))
    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        order.status=="未成交"

        content = u'stg_onorder收到的订单状态, statu:%s, id:%s, dealamount:%s'%(order.status, order.vtOrderID, order.tradedVolume)
        # mail('xxxx@xxx.com',content)   # 邮件模块可以将信息发送给策略师，第一个参数为邮件正文，第二个参数为策略name

        self.putEvent()

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交信息变化推送"""
        print("\n\n\n\n stg onTrade",trade.vtSymbol)

        self.opentime=trade.tradeTime
        self.putEvent()
    # ---------------------------------------------------------------------
    def onStopOrder(self, so):
        """停止单推送"""
        pass

if __name__=="__main__":
    from vnpy.trader.app.ctaStrategy.ctaBacktesting import BacktestingEngine, OptimizationSetting, MINUTE_DB_NAME
    # 创建回测引擎对象
    engine = BacktestingEngine()#初始化回测引擎
    # 设置回测使用的数据
    engine.setBacktestingMode(engine.BAR_MODE)    # 设置引擎的回测模式为K线,只会推送k线数据，如果改成TICK_MODE
    engine.setDatabase("VnTrader_1Min_Db")  # 设置使用的历史数据库，可以直接设置成数据库的名字比如Vn_1Min_Trader
    engine.setStartDate('20180103 10:00',initHours=24)               # 设置回测用的数据起始日期
    engine.setEndDate('20180925 10:00')
    # 配置回测引擎参数
    engine.setSlippage(0)     # 设置滑点为股指1跳
    engine.setRate(0)   # 设置手续费万0.3
    engine.setSize(1)         # 设置股指合约大小
    # engine.setPriceTick(0.0001)    # 设置股指最小价格变动
    engine.setCapital(1000000)  # 设置回测本金
    engine.calculateBacktestingResult()

    # # 在引擎中创建策略对象
    d = {'symbolList':["BTCUSDT:binance"]}          # 策略参数配置
    engine.initStrategy(Strategy_HighFrequency, d)    # 创建策略对象
    engine.runBacktesting()#开始回测
    engine.showBacktestingResult()
    engine.showDailyResult()
