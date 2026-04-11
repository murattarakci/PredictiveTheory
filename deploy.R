rsconnect::setAccountInfo(name='academic', 
                          token='D800569686F93FD621126CE392EC5074', 
                          secret='dEIIRMOfNU7s0ASIDQ8q3SWEdBwA9QSvgntJlaav')


rsconnect::deployApp(
    appDir = "/Users/murat.tarakci/Erasmus Universiteit Rotterdam Dropbox/Murat Tarakci/Research/Work in Progress/Predictive theorizing/Repo/WebApp",
    appName = "PredictiveTheorizing"
)

rsconnect add --account academic --name academic --token D800569686F93FD621126CE392EC5074 --secret dEIIRMOfNU7s0ASIDQ8q3SWEdBwA9QSvgntJlaav
rsconnect deploy shiny . --name PredictiveTheorizing

rsconnect deploy shiny . --name PredictiveTheorizing --account academic

rsconnect deploy shiny . --account academic