from stepwiseOptClass import stepwiseOpt
import numpy as np
import json
import os
from adxDiTmaStrategy import adxDiTmaStrategy

STRATEGYCLASS = adxDiTmaStrategy

# 指定引擎设置
ENGINESETTING = {
                "startDate": "20180701 00:00:00",
                "endDate": "20190501 23:59:00",
                "contract":[{
                             "slippage": 0.005,
                             "rate": 0.0008,
                           }],
                'setDB_URI': "mongodb://192.168.0.104:27017",
                "dbName": "VnTrader_1Min_Db",
                "symbolList":["eos.usd.q:okef"]
                }


# 优化目标
OPT_TARGET = "sharpeRatio"
# np.arange(0.1,0.2,0.01)
# range(1,10,1)
# 指定优化任务
OPT_TASK = [ 
            # {"pick_best_param": 
            #     {
            #      "timeframeMap" : 
            #      [
            #       {"envPeriod": "60m", "signalPeriod":"30m", "filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "60m", "signalPeriod":"15m", "filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "60m", "signalPeriod":"5m", "filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "30m", "signalPeriod":"30m", "filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "30m", "signalPeriod":"15m", "filterPeriod": "5m", "addPosPeriod":"5m"},
            #       {"envPeriod": "30m", "signalPeriod":"5m", "filterPeriod": "5m", "addPosPeriod":"5m"}
            #      ]
            #     }
            # }, 
            {"pick_freq_param": 
                {
                "adxPeriod": range(20,61,5),
                "adxThreshold": range(8,23,1)
                }
            }, 
            {"pick_best_param": 
                {
                "adxMaPeriod": range(10,51,5),
                "smaPeriod": range(20,61,5),
                }
            }, 
            {"pick_best_param": 
                {
                "lmaPeriod": range(60,191,10),
                "envMaPeriod": range(200,361,20),
                }
            }, 
            {"pick_best_param": 
                {
                "trailingPct": np.arange(0.016, 0.035, 0.002),
                "stopControlTime": range(1,9,1)
                }
            }, 
            # {"pick_best_param": 
            #     {
            #     "addPct": np.arange(0.002, 0.011, 0.002),
            #     "posTime": range(0,3,1)
            #     }
            # }, 
            {"pick_best_param": 
                {
                "takeProfitFirstPct": np.arange(0.03, 0.08, 0.01),
                "takeProfitSecondPct": np.arange(0.08, 0.19, 0.02)
                }
            }, 
            # {"pick_freq_param": 
            #     {
            #     "changeVolatilityPeriod": range(30,61,5),
            #     "erthreshold": np.arange(0.1, 0.23, 0.02)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "erSemaPeriod": range(8,23,2),
            #     "erLemaPeriod": range(25,41,2)
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "addVar": np.arange(0.5, 2.1, 0.5),
            #     "sign": ["+", "**", '*']
            #     }
            # }, 
            # {"pick_best_param": 
            #     {
            #     "takeProfitFirstPct": np.arange(0.04, 0.09, 0.005),
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