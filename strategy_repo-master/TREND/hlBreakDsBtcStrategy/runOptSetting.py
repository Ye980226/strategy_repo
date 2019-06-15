from stepwiseOptClass import stepwiseOpt
import numpy as np
import json
import os
from hlBreakDsStrategyV3 import hlBreakDsStrategy

STRATEGYCLASS = hlBreakDsStrategy

# 指定引擎设置
ENGINESETTING = {
                "startDate": "20180701 00:00:00",
                "endDate": "20190501 23:59:00",
                "contract":[{
                            "slippage": 0.5,
                            "rate": 0.0008,
                           }],
                'setDB_URI': "mongodb://192.168.0.104:27017",
                "dbName": "VnTrader_1Min_Db",
                "symbolList":["btc.usd.q:okef"]
                }


# 优化目标
OPT_TARGET = "sharpeRatio"
# np.arange(0.1,0.2,0.01)
# range(1,10,1)
# 指定优化任务
OPT_TASK = [
            {"pick_freq_param": 
                {
                "adxPeriod": range(10,51,5),
                "adxLowthreshold": range(8,23,2)
                }
            }, 
            {"pick_best_param": 
                {
                "adxHighthreshold": range(30,56,5),
                "adxMaxPeriod": range(10,51,10)
                }
            }, 
            {"pick_freq_param": 
                {
                "hlEntryPeriod": range(300,501,10),
                "hlExitPeriod": range(10,61,5)
                }
            }, 
            # {"pick_freq_param": 
            #     {
            #     "dsPeriod": range(20,61,5),
            #     "dsThreshold": np.arange(0.1, 0.23, 0.02)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "dsSemaPeriod": range(4,21,2),
            #     "dsLemaPeriod": range(25,51,5)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "addVar": np.arange(0.5, 1.6, 0.5),
            #     "sign": ["-", "+"]
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "takeProfitPct": np.arange(0.03, 0.09, 0.01),
            #     "posTime": range(1,4)
            #     }
            # }, 
]

# multiSymbolList = [
#                     # ['btc.usd.q:okef'],
#                     ['eos.usd.q:okef'],
#                     ['eth.usd.q:okef'],
#                     ['ltc.usd.q:okef']
#                   ]


def main():
    path = os.path.split(os.path.realpath(__file__))[0]
    with open(path+"//CTA_setting.json") as f:
        globalSetting = json.load(f)[0]

    # for s in multiSymbolList:
    #     ENGINESETTING["symbolList"] = s
    globalSetting.update(ENGINESETTING)
    optimizer = stepwiseOpt(STRATEGYCLASS, ENGINESETTING, OPT_TARGET, OPT_TASK, globalSetting, '../optResult')
    optimizer.runMemoryParallel()

if __name__ == '__main__':
    main()