# coding: utf-8
import datetime
from collections import defaultdict

import numpy as np
import pandas as pd
import talib as ta
from vnpy.trader.app.ctaStrategy.ctaTemplate import (ArrayManager,
                                                     BarGenerator, CtaTemplate)
from vnpy.trader.vtConstant import *


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
        self.passiveSymbol = self.symbolList[1]   # 被动品种
        self.activeDataSymbol=self.symbolList[2]#数据品种
        self.passiveDataSymbol=self.symbolList[3]
        self.pos=0
        # 构造K线合成器对象
        self.bgDict = {
            sym: BarGenerator(self.onBar)
            for sym in self.symbolList
        }
        self.activeDateTime=[]
        self.passiveDateTime=[]
        self.dataDateTime=[]
        self.alpha=0
        self.midPassiveBuffer=[]
        self.midActiveBuffer=[]
        self.barSpreadBuffer=[]
        # self.bg30Dict={
        #     sym: BarGenerator(self.onBar,30,self.on30MinBar)
        #     for sym in self.symbolList
        # }
        # self.amDict = {
        #     sym: ArrayManager(size=60*2+1)
        #     for sym in self.symbolList
        # }
        # self.am30Dict={
        #     sym:ArrayManager()#self.am10Dict[self.activeSymbol].updateBar(bar)会更新k线，ArrayManager默认size是100，就是缓存一个100个的数组的open，high，low，close数据
        #     for sym in self.symbolList
        # }
        self.tickBufferDict={sym:[] for sym in self.symbolList}
        self.barBufferDict={sym:[] for sym in self.symbolList}
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
        self.miu=0
        self.gap=0
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
        self.tickBufferDict[tick.vtSymbol].append(tick)
        
       #保证两边都有数据才开始进行后面的交易
        if not self.tickBufferDict[self.activeSymbol]:
            return 
        if not self.tickBufferDict[self.passiveSymbol]:
            return
        if not self.tickBufferDict[self.activeDataSymbol]:
            return 
        if not self.tickBufferDict[self.passiveDataSymbol]:
            return 
        if len(self.tickBufferDict[self.activeSymbol])>=50 and len(self.tickBufferDict[self.passiveSymbol])>=50 and len(self.tickBufferDict[self.activeDataSymbol])>=50 and len(self.tickBufferDict[self.passiveDataSymbol])>=150:
            del self.tickBufferDict[self.activeSymbol][:-10]
            del self.tickBufferDict[self.passiveSymbol][:-10]
            del self.tickBufferDict[self.activeDataSymbol][:-10]
            del self.tickBufferDict[self.passiveDataSymbol][:-10]
        #流动性差的品种的bid1和ask1的均值作为计pread的价格
        midPassive=(self.tickBufferDict[self.passiveSymbol][-1].askPrice1+self.tickBufferDict[self.passiveSymbol][-1].bidPrice1)/2
        #流动性好的品种的bid1和ask1的均值作为计算spread的价格
        midActive=(self.tickBufferDict[self.activeSymbol][-1].askPrice1+self.tickBufferDict[self.activeSymbol][-1].bidPrice1)/2
        #用passive的Buffer存下来midPassive，方便计算均值
        self.midPassiveBuffer.append(midPassive)
        #用active的Buffer存下来midActive，方便计算均值
        self.midActiveBuffer.append(midActive)
        beta=self.tickBufferDict[self.activeDataSymbol][-1].lastPrice/self.tickBufferDict[self.passiveDataSymbol][-1].lastPrice
        #用spread表示价差，但该价差是假定beta=1的时候算-self.alpha出来的，线性回归的sigma（残差）
        spread=midActive-midPassive*beta-self.alpha
        if (not self.miu) or (not self.gap):
            return 
        # self.spreadBuffer.append(spread)
        
        # if len(self.spreadBuffer)==50:
            # del self.spreadBuffer[:-10]
            
        
        #买价-卖价
        # abpassive = self.tickBufferDict[self.passiveSymbol][-1].askPrice1 - self.tickBufferDict[self.passiveSymbol][-1].bidPrice1
        # abactive = self.tickBufferDict[self.activeSymbol][-1].askPrice1 - self.tickBufferDict[self.activeSymbol][-1].bidPrice1
        
        # bid_askSpread=self.tickBufferDict[self.activeSymbol][-1].bidPrice1-self.tickBufferDict[self.activeSymbol][-1].askPrice1
        # self.cost = 1/2*(abpassive + abactive)+ \
            #    2*0.0005*(self.tickBufferDict[self.activeSymbol][-1].lastPrice + self.tickBufferDict[self.passiveSymbol][-1].lastPrice)          
    
        '''
        在每个Tick推送过来的时候,进行updateTick,生成分钟线后推送到onBar. 
        注：如果没有updateTick，将不会推送分钟bar
        '''
        if self.pos==0:
            if spread>self.miu+self.gap:
                self.short(self.activeSymbol,1,1)
                self.buy(self.passiveSymbol, 99999, self.size)
                print("开看空")
                self.cover_size=self.size
                self.cover_miu=self.miu
                self.cover_gap=self.gap
                self.pos = 1
                return 
            if spread<self.miu-self.gap:
                self.buy(self.activeSymbol,99999,1)
                self.short(self.passiveSymbol, 1, self.size)
                print("开看跌")
                self.cover_size=self.size
                self.cover_miu=self.miu
                self.cover_gap=self.gap
                self.pos = -1
                return 
        if self.pos == 1 and spread < self.cover_miu - self.cover_gap  and self.posDict[self.activeSymbol+"_SHORT"]>0 and self.posDict[self.passiveSymbol+"_LONG"]>0:
            
            self.cover(self.activeSymbol,99999,1)
            self.sell(self.passiveSymbol,1,self.cover_size)
            self.pos = 0
            print("平看空")            
        if self.pos==-1 and spread>self.cover_miu+self.cover_gap  and self.posDict[self.activeSymbol+"_LONG"]>0 and self.posDict[self.passiveSymbol+"_SHORT"]>0:
            self.sell(self.activeSymbol,1,1)
            self.cover(self.passiveSymbol,99999,self.cover_size)
            self.pos = 0
            print("平看多")
    # ----------------------------------------------------------------------
    def onBar(self,bar):
        """收到1分钟K线推送"""
        # self.bg30Dict[bar.vtSymbol].updateBar(bar)
        if bar.datetime>datetime.datetime.now():
            return 
        self.barBufferDict[bar.vtSymbol].append(bar.close)
        if len(self.barBufferDict[self.activeSymbol])>240 and len(self.barBufferDict[self.passiveSymbol])>240 and len(self.barBufferDict[self.activeDataSymbol])>240 and len(self.barBufferDict[self.passiveDataSymbol])>240:
            x=np.array(self.barBufferDict[self.activeSymbol][-240:])
            y=np.array(self.barBufferDict[self.passiveSymbol][-240:])
            beta=np.array(self.barBufferDict[self.passiveDataSymbol][-240:])/np.array(self.barBufferDict[self.activeDataSymbol][-240:])
            spread=y-beta*x
            self.size=int(np.mean(beta))
            self.miu=np.mean(spread)
            self.gap=np.mean(y+beta*x)/2*0.002
            del self.barBufferDict[self.activeSymbol][:-120]
            del self.barBufferDict[self.passiveSymbol][:-120]
            del self.barBufferDict[self.activeDataSymbol][:-120]
            del self.barBufferDict[self.passiveDataSymbol][:-120]
        # if bar.vtSymbol==self.activeSymbol:
        #     if len(self.activeDateTime)==0:
        #         self.writeCtaLog("第一次更新bar.datetime")                
        #         self.barBufferDict[self.activeSymbol].append(bar.close)
        #         self.activeDateTime.append(bar.datetime)
        #         self.writeCtaLog("activeSymbol的bar.close数组的长度%s"%len(self.barBufferDict[self.activeSymbol]))
        #         if len(self.passiveDateTime)==0:
        #             return 
        #         elif (bar.datetime-self.passiveDateTime[-1]).total_seconds()<=5:
        #             if len(self.barBufferDict[self.passiveSymbol])==0:
        #                 return
        #             self.barSpreadBuffer.append(bar.close-self.barBufferDict[self.passiveSymbol][-1]-self.alpha)
        #             self.writeCtaLog("passiveSymbol先到更新价差")
        #             self.writeCtaLog("barSpreadBuffer的长度为:%s"%(len(self.barSpreadBuffer)))
        #     elif (bar.datetime-self.activeDateTime[-1]).total_seconds()>=55:
        #         self.activeDateTime.append(bar.datetime)
        #         self.barBufferDict[self.activeSymbol].append(bar.close)
        #         self.writeCtaLog("activeSymbol的bar.close数组的长度%s"%len(self.barBufferDict[self.activeSymbol]))
        #         if len(self.passiveDateTime)==0:
        #             return 
        #         elif (bar.datetime-self.passiveDateTime[-1]).total_seconds()<=5:
        #             if len(self.barBufferDict[self.passiveSymbol])==0:
        #                 return
        #             self.barSpreadBuffer.append(bar.close-self.barBufferDict[self.passiveSymbol][-1]-self.alpha)
        #             self.writeCtaLog("passiveSymbol先到更新价差")
        #             self.writeCtaLog("barSpreadBuffer的长度为:%s"%(len(self.barSpreadBuffer)))
        # if bar.vtSymbol==self.passiveSymbol:
        #     if len(self.passiveDateTime)==0:
        #         self.passiveDateTime.append(bar.datetime)
        #         self.barBufferDict[self.passiveSymbol].append(bar.close)
        #         self.writeCtaLog("passiveSymbol的bar.close数组的长度%s"%len(self.barBufferDict[self.passiveSymbol]))
        #         self.writeCtaLog("第一次更新bar.datetime")
        #         if len(self.activeDateTime)==0:
        #             return
        #         elif (bar.datetime-self.activeDateTime[-1]).total_seconds()<=5:
        #             if len(self.barBufferDict[self.activeSymbol])==0:
        #                 return
        #             self.barSpreadBuffer.append(self.barBufferDict[self.activeSymbol][-1]-bar.close-self.alpha)
        #             self.writeCtaLog("activeSymbol先到更新价差")
        #             self.writeCtaLog("barSpreadBuffer的长度为:%s"%(len(self.barSpreadBuffer)))
        #     elif (bar.datetime-self.passiveDateTime[-1]).total_seconds()>=55:
        #         self.passiveDateTime.append(bar.datetime)
        #         self.barBufferDict[self.passiveSymbol].append(bar.close)
        #         self.writeCtaLog("passiveSymbol的bar.close数组的长度%s"%len(self.barBufferDict[self.passiveSymbol]))
        #         if len(self.activeDateTime)==0:
        #             return
        #         elif (bar.datetime-self.activeDateTime[-1]).total_seconds()<=5:
        #             if len(self.barBufferDict[self.activeSymbol])==0:
        #                 return
        #             self.barSpreadBuffer.append(self.barBufferDict[self.activeSymbol][-1]-bar.close-self.alpha)
        #             self.writeCtaLog("activeSymbol先到更新价差")
        #             self.writeCtaLog("barSpreadBuffer的长度为:%s"%(len(self.barSpreadBuffer)))
        # if bar.vtSymbol==self.dataSymbol:
        #     self.dataDateTime.append(bar.datetime)
        #     self.barBufferDict[self.dataSymbol].append(bar.close)
    def on30MinBar(self,bar):
        # self.amDict[bar.vtSymbol].updateBar(bar)
        
        self.putEvent()
        pass

    def onhfBar(self,bar):
        self.writeCtaLog("%s, %s,444444444444444444,%s"%(bar.datetime,bar.vtSymbol,bar.close))
    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # order.status=="未成交"

        # content = u'stg_onorder收到的订单状态, statu:%s, id:%s, dealamount:%s'%(order.status, order.vtOrderID, order.tradedVolume)
        # mail('xxxx@xxx.com',content)   # 邮件模块可以将信息发送给策略师，第一个参数为邮件正文，第二个参数为策略name
        
        self.writeCtaLog("order.status %s order.vtSymbol %s order.vtOrderID %s order.direction %s order.offset %s order.price:%s"%(order.status,order.vtSymbol,order.vtOrderID,order.offset,order.direction,order.price))        
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
    engine.setBacktestingMode(engine.TICK_MODE)    # 设置引擎的回测模式为K线,只会推送k线数据，如果改成TICK_MODE
    engine.setDatabase("VnTrader_Tick_Db")  # 设置使用的历史数据库，可以直接设置成数据库的名字比如Vn_1Min_Trader
    engine.setStartDate('20180903 10:00',initHours=24)               # 设置回测用的数据起始日期
    engine.setEndDate('20180910 10:00')
    # 配置回测引擎参数
    engine.setSlippage(0)     # 设置滑点为股指1跳
    engine.setRate(0)   # 设置手续费万0.3
    engine.setSize(1)         # 设置股指合约大小
    # engine.setPriceTick(0.0001)    # 设置股指最小价格变动
    engine.setCapital(1000000)  # 设置回测本金
    engine.calculateBacktestingResult()

    # # 在引擎中创建策略对象
    d = {'symbolList':["eth_this_week:OKEX","eos_this_week:OKEX","eth_usdt:OKEX","eos_usdt:OKEX"]}          # 策略参数配置
    engine.initStrategy(Strategy_HighFrequency, d)    # 创建策略对象
    engine.runBacktesting()#开始回测
    engine.showBacktestingResult()
    engine.showDailyResult()
