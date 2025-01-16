# -*- coding: utf-8 -*-
import sys
import time
from datetime import datetime
import tzlocal
import serial
import serial.tools.list_ports
import sqlite3
import time
import random
import math
import logging
from PySide import QtGui, QtCore, QtWebKit
from PySide.QtOpenGL import *
import numpy as np
import pyqtgraph as pg

pg.setConfigOptions(antialias=True)

VERSION = '1.0.0'
max_graph_length = 18
delta_s = 100
dn = 3

class Globals():
    temp = 0.1
    press = 0.1
    poll = 0.1
    accel = [0.1, 0.1, 0.1]

class Timing():
    timer = QtCore.QTimer()
    slowTimer = QtCore.QTimer()
    passiveTimer = QtCore.QTimer()

# ----------------------------------------------------------------------
# Utils
# ----------------------------------------------------------------------

class Notice():
    def __init__(self):
        self.allId = {}
        Timing.passiveTimer.timeout.connect(self.reset)

    def defineNotice(self, text):
        self.allId[text[0:3]] = 0

    def notice(self, text):
        try:
            key = text[0:3]
            if self.allId[key] == 0:
                print text
                self.allId[key] = 1
        except KeyError:
            self.defineNotice(text)

    def reset(self):
        self.allId = {}

notice = Notice()

# ----------------------------------------------------------------------
# Input
# ----------------------------------------------------------------------

class Arduino():
    def __init__(self):
        self.NP = '-1'
        self.data = [0.1, 0.1, 0.1]
        self.tempStatus = False
        self.pressStatus = False
        self.pollStatus = False
        self.debugMode = False
        self.comStatus = False
        try:
            self.connect()
            self.comStatus = True
        except Exception as e:
            print e
            self.debugMode = True

    def findPort(self, device="Arduino Leonardo"):
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            port = str(port)
            if device in port:
                np = filter(str.isdigit, port.split(' ')[0])
                self.NP = np

    def connect(self):
        self.findPort()
        self.arduino = serial.Serial('COM' + self.NP, 9600, timeout=0)

    def retryConn(self):
        self.arduino.close()
        for x in xrange(1):
            try:
                self.connect()
                self.comStatus = True
                print '00B-Signal found'
                break
            except:
                continue

    def getData(self, i):
        if not self.debugMode:
            try:
                output = self.arduino.readline().strip()
            except:
                notice.notice('00A-Lost signal')
                self.tempStatus = False
                self.pressStatus = False
                self.pollStatus = False
                self.comStatus = False
                self.retryConn()
                return self.data

            if len(output) > 2:
                data = output.split(',')

                try:
                    temp = float(data[0])
                    self.tempStatus = True
                except:
                    temp = 0.1
                    self.tempStatus = False

                try:
                    press = float(data[1])
                    self.pressStatus = True
                except:
                    press = 0.1
                    self.pressStatus = False

                try:
                    poll = float(data[2])
                    self.pollStatus = True
                except:
                    poll = 0.1
                    self.pollStatus = False

                self.data = [temp, press, poll]
        return self.data

arduino = Arduino()

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

class QtHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)

    def emit(self, record):
        record = self.format(record)
        if record: XStream.stdout().write('%s\n' %(record))

logger = logging.getLogger(__name__)
handler = QtHandler()
handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

class XStream(QtCore.QObject):
    _stdout = None
    _stderr = None
    messageWritten = QtCore.Signal(str)

    def flush(self):
        pass

    def fileno(self):
        return -1

    def write(self, msg):
        if not self.signalsBlocked():
            self.messageWritten.emit(unicode(msg))

    @staticmethod
    def stdout():
        if not XStream._stdout:
            XStream._stdout = XStream()
            sys.stdout = XStream._stdout
        return XStream._stdout

    @staticmethod
    def stderr():
        if not XStream._stderr:
            XStream._stderr = XStream()
            sys.stderr = XStream._stderr
        return XStream._stderr

class LogsBox(QtGui.QTextBrowser):
    def __init__(self):
        super(LogsBox, self).__init__()
        self.document().setMaximumBlockCount(10000)

        self.oldMax = self.verticalScrollBar().value()

        Timing.timer.timeout.connect(self.update)

    def update(self):
        if self.verticalScrollBar().value() >= self.oldMax:
            self.autoscroll()
            self.oldMax = self.verticalScrollBar().value()

    def autoscroll(self):
        self.moveCursor(QtGui.QTextCursor.End)
        self.ensureCursorVisible()

class Logger(QtGui.QWidget):
    def __init__(self):
        super(Logger, self).__init__()
        self.logsBox = LogsBox()

        layout = QtGui.QVBoxLayout()
        layout.addWidget(self.logsBox)
        self.setLayout(layout)

        XStream.stdout().messageWritten.connect(self.logsBox.insertPlainText)
        XStream.stderr().messageWritten.connect(self.logsBox.insertPlainText)

# ----------------------------------------------------------------------
# Data recording
# ----------------------------------------------------------------------

class SQLite():
    def __init__(self):
        self.conn = sqlite3.connect('cansat-records-strv%s.db' %(VERSION))
        self.c = self.conn.cursor()

        try:
            self.c.execute('CREATE TABLE temp(date datetime, value real, um text)')
        except sqlite3.OperationalError:
            pass

        try:
            self.c.execute('CREATE TABLE press(date datetime, value real, um text)')
        except sqlite3.OperationalError:
            pass

        try:
            self.c.execute('CREATE TABLE poll(date datetime, value real, um text)')
        except sqlite3.OperationalError:
            pass

    def addRecords(self):
        self.time = time.strftime('%Y-%m-%d %H:%M:%S')
        self.c.execute("INSERT INTO temp VALUES (?, ?, 'K')", (self.time, format(Globals.temp, '.3f')))
        self.c.execute("INSERT INTO press VALUES (?, ?, 'Pa')", (self.time, Globals.press))
        self.c.execute("INSERT INTO poll VALUES (?, ?, 'pcs/L')", (self.time, Globals.poll))
        self.conn.commit()

    def close(self):
        self.conn.close()
# ----------------------------------------------------------------------
# Math Tools
# ----------------------------------------------------------------------

def interquartileMean(l):
    l = sorted(l)
    n = len(l)
    mean = 2.0/n * sum([l[int(round(n/4.0+x))] for x in xrange(int(round(3.0*n/6.0)))])
    return mean

# ----------------------------------------------------------------------
# Tools
# ----------------------------------------------------------------------

def meanList(self, k):
    l = self.meanList
    l.append(k)
    self.mean = np.mean(l)

# ----------------------------------------------------------------------
# Update
# ----------------------------------------------------------------------

def update(self):
    now = time.clock()
    data = eval(self.scale %(float(arduino.getData(0)[self.ind])))
    self.array[self.p+1, 0] = now
    self.array[self.p+1, 1] = data
    self.curve.setData(x=self.array[:self.p+2:, 0], y=self.array[:self.p+2, 1])
    self.p += 1
    self.data[0] = data

def meanUpdate(self):
    now = time.clock()
    self.mArray[self.m_p+1, 0] = now
    self.mArray[self.m_p+1, 1] = self.mean
    self.mCurve.setData(x=self.mArray[:self.m_p+2:, 0], y=self.mArray[:self.m_p+2, 1])
    self.m_p += 1

# ----------------------------------------------------------------------
# Top bar widget
# ----------------------------------------------------------------------

WORKING_COLOR = '#090'
ERROR_COLOR = '#f00'

class StatusViewer(QtGui.QLabel):
    def __init__(self):
        super(StatusViewer, self).__init__()
        self.image = ''

        Timing.slowTimer.timeout.connect(self.update)

    def update(self):
        imgTemp = self.image
        if arduino.debugMode == True or \
            arduino.tempStatus == False or \
            arduino.pressStatus == False or \
            arduino.pollStatus == False or \
            arduino.comStatus == False:
            self.image = 'media\\red_led.png'
        else:
            self.image = 'media\\green_led.png'

        if imgTemp != self.image:
            self.setText('<img src="%s"> &nbsp; Status' %(self.image))

class SerialViewer(QtGui.QLabel):
    def __init__(self):
        super(SerialViewer, self).__init__()
        self.setText('COM: ' + arduino.NP)

        Timing.timer.timeout.connect(self.update)

    def update(self):
        npTemp = arduino.NP
        if arduino.debugMode == False and arduino.comStatus == True:
            self.setStyleSheet('.SerialViewer{color:%s;}' %(WORKING_COLOR))
        else:
            self.setStyleSheet('.SerialViewer{color:%s;}' %(ERROR_COLOR))

        """if imgTemp != arduino.NP:
            self.setText('COM: ' + arduino.NP)"""

class TempViewer(QtGui.QLabel):
    def __init__(self):
        super(TempViewer, self).__init__()
        self.setText('BMP180 - Temp')

        Timing.timer.timeout.connect(self.update)

    def update(self):
        if arduino.tempStatus == False:
            self.setStyleSheet('.TempViewer{color:%s;}' %(ERROR_COLOR))
        else:
            self.setStyleSheet('.TempViewer{color:%s;}' %(WORKING_COLOR))

class PressViewer(QtGui.QLabel):
    def __init__(self):
        super(PressViewer, self).__init__()
        self.setText('BMP180 - Press')

        Timing.timer.timeout.connect(self.update)

    def update(self):
        if arduino.pressStatus == False:
            self.setStyleSheet('.PressViewer{color:%s;}' %(ERROR_COLOR))
        else:
            self.setStyleSheet('.PressViewer{color:%s;}' %(WORKING_COLOR))

class PollViewer(QtGui.QLabel):
    def __init__(self):
        super(PollViewer, self).__init__()
        self.setText('PPD42NS - Dust concn')

        Timing.timer.timeout.connect(self.update)

    def update(self):
        if arduino.pollStatus == False:
            self.setStyleSheet('.PollViewer{color:%s;}' %(ERROR_COLOR))
        else:
            self.setStyleSheet('.PollViewer{color:%s;}' %(WORKING_COLOR))

class DateTimeViewer(QtGui.QLabel):
    def __init__(self):
        super(DateTimeViewer, self).__init__()
        self.time = 'Date: &nbsp; Time: '
        self.setText(self.time)

        Timing.timer.timeout.connect(self.update)

    def update(self):
        now = datetime.now(tzlocal.get_localzone())
        self.time = now.strftime('Date: %Y-%m-%d &nbsp; Time: %H:%M:%S')
        self.millis = now.strftime('.%f ')[:-4]
        self.tz = now.strftime('%z')
        self.setText('%s<span style="font-size:11px;">%s</span> &nbsp; GMT %s'%(self.time, self.millis, self.tz))

class ETViewer(QtGui.QLabel):
    def __init__(self):
        super(ETViewer, self).__init__()
        self.sTime = time.time()
        self.text = 'Elapsed time: %.3f s'
        self.setText(self.text)

        Timing.timer.timeout.connect(self.update)

    def update(self):
        et = round(time.time() - self.sTime, 3)
        self.setText(self.text %(et))

# ----------------------------------------------------------------------
# General control widget
# ----------------------------------------------------------------------

class TopBar(QtGui.QFrame):
    def __init__(self):
        super(TopBar, self).__init__()
        self.layout = QtGui.QHBoxLayout()
        self.layout.setAlignment(QtCore.Qt.AlignLeft)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 2, 0, 2)
        
        self.statusViewer = StatusViewer()
        self.serialViewer = SerialViewer()
        self.dateTimeViewer = DateTimeViewer()
        self.etViewer = ETViewer()
        self.tempViewer = TempViewer()
        self.pressViewer = PressViewer()
        self.pollViewer = PollViewer()

        self.layout.addWidget(self.statusViewer, 0, 0)
        self.layout.addWidget(self.serialViewer, 0, 1)
        self.layout.addWidget(self.dateTimeViewer, 0, 2)
        self.layout.addWidget(self.etViewer, 0, 3)
        self.layout.addWidget(self.tempViewer, 0, 4)
        self.layout.addWidget(self.pressViewer, 0, 5)
        self.layout.addWidget(self.pollViewer, 0, 6)
        self.setLayout(self.layout)

class LockOpt(QtGui.QCheckBox):
    def __init__(self, graph):
        super(LockOpt, self).__init__()
        self.setCheckState(QtCore.Qt.Unchecked)

        self.label = QtGui.QLabel()
        self.label.setText('Lock graph')

        self.graph = graph

        self.stateChanged.connect(self.lockGraph)

    def lockGraph(self, x):
        if isinstance(self.graph, basestring):
            self.graph = eval(self.graph)

        if x == 2:
            self.graph.setMouseEnabled(x=False, y=False)
            self.graph.setMenuEnabled(False)
        else:
            self.graph.setMouseEnabled(x=True, y=True)
            self.graph.setMenuEnabled(True)

class ResetView(QtGui.QPushButton):
    def __init__(self, graph):
        super(ResetView, self).__init__()
        self.setText('Reset view')

        self.graph = graph

        self.clicked.connect(self.resetView)

    def resetView(self):
        if isinstance(self.graph, basestring):
            self.graph = eval(self.graph)

        self.graph.setView()

# ----------------------------------------------------------------------
# Preferences
# ----------------------------------------------------------------------

def changeScale(self):
    graph = eval(self.graph)
    graph.scale = 'self.' + self.currentText().lower() + '(%s)'
    graph.setLabel('left', graph.name, self.currentText()[0])
    yRange = (self.deltas[self.currentText()[0]][0], self.deltas[self.currentText()[0]][1])
    graph.setYRange(yRange[0], yRange[1])

    graph.yRange = (yRange[0], yRange[1])

    graph.data[1] = self.currentText()[0]

    graph.changed = 0

    if self.hasMean == True:
        convertMean(self, graph)

    # Adjusting graph
    convertGraph(self, graph.curve, graph)
    convertGraph(self, graph.mCurve, graph)

    self.prevScale = self.currentText()[0]

def convertGraph(self, curve, graph):
    array = curve.getData()
    for i, y in enumerate(array[1]):
        array[1][i] = eval(self.convert[self.prevScale + self.currentText()[0]].format(y))
    curve.setData(x=array[0], y=array[1])

def convertMean(self, graph):
    for i, v in enumerate(graph.meanList):
        graph.meanList[i] = eval(self.convert[self.prevScale + self.currentText()[0]].format(v))

# ----------------------------------------------------------------------
# Temperature
# ----------------------------------------------------------------------

class ChangeTempUM(QtGui.QComboBox):
    def __init__(self):
        super(ChangeTempUM, self).__init__()
        self.addItems(('Kelvin', 'Celsius', 'Fahrenheit'))
        self.setMaximumWidth(120)

        self.graph = 'window.mainWidget.mainLayout.plottingFrame.plottingLayout.tempGraph'
        self.hasMean = True

        self.prevScale = 'K'
        self.deltas = {'K' : (290, 310), 'C' : (17, 37), 'F' : (62, 98)}

        self.convert = {
            'CK' : '{0} + 273.15',
            'KC' : '{0} - 273.15',
            'CF' : '{0} * 1.8 + 32',
            'FC' : '({0} - 32) / 1.8',
            'KF' : '({0} - 273.15) * 1.8 + 32',
            'FK' : '({0} - 32) / 1.8 + 273.15'
        }

        self.label = QtGui.QLabel()
        self.label.setText('U.M.')

        self.currentIndexChanged.connect(lambda: changeScale(self))

class ControlTempLayout(QtGui.QGridLayout):
    def __init__(self):
        super(ControlTempLayout, self).__init__()
        self.setSpacing(5)
        self.setContentsMargins(10, 10, 10, 10)
        self.setAlignment(QtCore.Qt.AlignTop)

        self.prefsGroup = QtGui.QGroupBox('Preferences/Settings')
        self.prefsLayout = QtGui.QGridLayout()
        self.prefsLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.prefsGroup.setLayout(self.prefsLayout)

        self.optionsGroup = QtGui.QGroupBox('Options')
        self.optionsLayout = QtGui.QGridLayout()
        self.optionsLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.optionsGroup.setLayout(self.optionsLayout)

        self.othersGroup = QtGui.QGroupBox()
        self.othersLayout = QtGui.QGridLayout()
        self.othersLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.othersGroup.setLayout(self.othersLayout)

        temp_path = 'window.mainWidget.mainLayout.plottingFrame.plottingLayout.tempGraph'
        self.changeTempUM = ChangeTempUM()
        self.lockOpt = LockOpt(temp_path)
        self.resetView = ResetView(temp_path)

        self.prefsLayout.addWidget(self.changeTempUM.label, 0, 0)
        self.prefsLayout.addWidget(self.changeTempUM, 0, 1)
        self.optionsLayout.addWidget(self.lockOpt.label, 0, 0)
        self.optionsLayout.addWidget(self.lockOpt, 0, 1)
        self.othersLayout.addWidget(self.resetView, 0, 0)

        self.addWidget(self.prefsGroup)
        self.addWidget(self.optionsGroup)
        self.addWidget(self.othersGroup)

class ControlTemp(QtGui.QTabWidget):
    def __init__(self):
        super(ControlTemp, self).__init__()
        self.controlTempLayout = ControlTempLayout()
        self.setLayout(self.controlTempLayout)

class TempGraph(pg.PlotWidget):
    def __init__(self, plotLayout):
        super(TempGraph, self).__init__()
        self.setLabel('left', 'Temperature', 'K')
        self.setLabel('bottom', 'Time', 's')
        self.addLegend()

        self.yRange = (290, 310)

        self.setView()

        self.meanTimer = QtCore.QTimer()
        self.meanTimer.start(2000)

        # Identity
        self.name = 'Temperature'
        self.setTitle(self.name)

        # Graph vars
        self.plotLayout = plotLayout
        self.chunkSize = 150000

        self.array = np.empty((self.chunkSize + 1, 2))
        self.p = 0

        self.mArray = np.empty((self.chunkSize + 1, 2))
        self.m_p = 0

        self.ind = 0
        self.changed = 1

        # Vars
        self.maxCurves = max_graph_length
        self.colour = '#ff0000'
        self.scale = 'self.kelvin(%s)'
        self.data = [0, 'K']

        self.meanList = []
        self.mean = 0

        self.curve = self.plot(pen=self.colour, name=self.name)
        self.mCurve = self.plot(pen=pg.mkPen(color=self.colour, style=QtCore.Qt.DotLine), name='Mean ' + self.name)

    def start(self):
        # Events
        Timing.timer.timeout.connect(lambda: update(self))
        self.meanTimer.timeout.connect(lambda: meanList(self, float(self.data[0])))
        self.meanTimer.timeout.connect(lambda: meanUpdate(self))

    def setView(self):
        self.setXRange(0, delta_s)
        self.setYRange(self.yRange[0], self.yRange[1])
        self.showGrid(x=1, y=1, alpha=0.35)
        self.enableAutoRange('x')

    def celsius(self, inpt):
        if self.changed == 0:
            self.mean = str(float(self.mean) - 273.15)

            for value in self.meanList:
                value -= 273.15

            self.changed = 1

        Globals.temp = inpt + 273.15

        return inpt

    def kelvin(self, inpt):
        if self.changed == 0:
            self.mean = str(float(self.mean) + 273.15)

            for value in self.meanList:
                value += 273.15

            self.changed = 1

        Globals.temp = inpt + 273.15

        return inpt + 273.15

    def fahrenheit(self, inpt):
        if self.changed == 0:
            self.mean = str(float(self.mean) * 1.8 + 32)

            for value in self.meanList:
                value = value * 1.8 + 32

            self.changed = 1

        Globals.temp = inpt + 273.15

        return inpt * 1.8 + 32

# ----------------------------------------------------------------------
# Pressure
# ----------------------------------------------------------------------

class ControlPressLayout(QtGui.QGridLayout):
    def __init__(self):
        super(ControlPressLayout, self).__init__()
        self.setSpacing(5)
        self.setContentsMargins(10, 10, 10, 10)
        self.setAlignment(QtCore.Qt.AlignTop)

        self.optionsGroup = QtGui.QGroupBox('Options')
        self.optionsLayout = QtGui.QGridLayout()
        self.optionsLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.optionsGroup.setLayout(self.optionsLayout)

        self.othersGroup = QtGui.QGroupBox()
        self.othersLayout = QtGui.QGridLayout()
        self.othersLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.othersGroup.setLayout(self.othersLayout)

        temp_path = 'window.mainWidget.mainLayout.plottingFrame.plottingLayout.pressureGraph'
        self.lockOpt = LockOpt(temp_path)
        self.resetView = ResetView(temp_path)

        self.optionsLayout.addWidget(self.lockOpt.label, 0, 0)
        self.optionsLayout.addWidget(self.lockOpt, 0, 1)
        self.othersLayout.addWidget(self.resetView, 0, 0)

        self.addWidget(self.optionsGroup)
        self.addWidget(self.othersGroup)

class ControlPressure(QtGui.QTabWidget):
    def __init__(self):
        super(ControlPressure, self).__init__()
        self.controlPressLayout = ControlPressLayout()
        self.setLayout(self.controlPressLayout)

class PressureGraph(pg.PlotWidget):
    def __init__(self, plotLayout):
        super(PressureGraph, self).__init__()
        self.setLabel('left', 'Pressure', 'Pa')
        self.setLabel('bottom', 'Time', 's')
        self.addLegend()

        self.setView()

        # Identity
        self.name = 'Pressure'
        self.setTitle(self.name)

        # Graph vars
        self.plotLayout = plotLayout
        self.chunkSize = 150000
        self.array = np.empty((self.chunkSize + 1, 2))
        self.p = 0

        self.ind = 1

        # Vars
        self.initState = self.saveState()
        self.maxCurves = max_graph_length
        self.colour = '#00ff00'
        self.scale = 'self.pascal(%s)'
        self.data = [0, 'Pa']

        self.curve = self.plot(pen=self.colour, name=self.name)

    def start(self):
        # Events
        Timing.timer.timeout.connect(lambda: update(self))

    def setView(self):
        self.setXRange(0, delta_s)
        self.setYRange(80000, 130000)
        self.showGrid(x=1, y=1, alpha=0.35)
        self.enableAutoRange('x')

    def pascal(self, inpt):
        value = inpt * 100

        Globals.press = value

        return value

# ----------------------------------------------------------------------
# Poll
# ----------------------------------------------------------------------

class ControlPollLayout(QtGui.QGridLayout):
    def __init__(self):
        super(ControlPollLayout, self).__init__()
        self.setSpacing(5)
        self.setContentsMargins(10, 10, 10, 10)
        self.setAlignment(QtCore.Qt.AlignTop)

        self.optionsGroup = QtGui.QGroupBox('Options')
        self.optionsLayout = QtGui.QGridLayout()
        self.optionsLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.optionsGroup.setLayout(self.optionsLayout)

        self.othersGroup = QtGui.QGroupBox()
        self.othersLayout = QtGui.QGridLayout()
        self.othersLayout.setAlignment(QtCore.Qt.AlignLeft)
        self.othersGroup.setLayout(self.othersLayout)

        temp_path = 'window.mainWidget.mainLayout.plottingFrame.plottingLayout.pollGraph'
        self.lockOpt = LockOpt(temp_path)
        self.resetView = ResetView(temp_path)

        self.optionsLayout.addWidget(self.lockOpt.label, 0, 0)
        self.optionsLayout.addWidget(self.lockOpt, 0, 1)
        self.othersLayout.addWidget(self.resetView, 0, 0)

        self.addWidget(self.optionsGroup)
        self.addWidget(self.othersGroup)

class ControlPoll(QtGui.QTabWidget):
    def __init__(self):
        super(ControlPoll, self).__init__()
        self.controlPollLayout = ControlPollLayout()
        self.setLayout(self.controlPollLayout)

class PollGraph(pg.PlotWidget):
    def __init__(self, plotLayout):
        super(PollGraph, self).__init__()
        self.setLabel('left', 'Dust concn', 'pcs/L')
        self.setLabel('bottom', 'Time', 's')
        self.addLegend()

        self.setView()
        self.setDownsampling(mode='peak')

        # Identity
        self.name = 'Air quality'
        self.setTitle(self.name)

        self.plotLayout = plotLayout
        self.chunkSize = 150000
        self.array = np.empty((self.chunkSize + 1, 2))
        self.p = 0

        self.ind = 2

        # Vars
        self.initState = self.saveState()
        self.maxCurves = max_graph_length
        self.colour = '#0000ff'
        self.scale = 'self.pcsL(%s)'
        self.data = [0, 'pcs/L']

        self.curve = self.plot(pen=self.colour, name=self.name)

    def start(self):
        # Events
        Timing.timer.timeout.connect(lambda: update(self))

    def setView(self):
        self.setXRange(0, delta_s)
        self.setYRange(0, 40000)
        self.showGrid(x=1, y=1, alpha=0.35)
        self.enableAutoRange('x')

    def pcsL(self, inpt):
        Globals.poll = inpt
        return inpt


# ----------------------------------------------------------------------
# Obtained
# ----------------------------------------------------------------------
def hypsometricFormula(P0):
    P = float(Globals.press)
    a = float((P0 / P)**(1 / 5.257) - 1)
    b = float(Globals.temp)
    altitude = (a * b) / 0.0065
    return str(altitude)

# ----------------------------------------------------------------------
# General
# ----------------------------------------------------------------------

class ControlFrame(QtGui.QTabWidget):
    def __init__(self):
        super(ControlFrame, self).__init__()
        self.graphs = QtGui.QTabWidget()
        self.controlTemp = ControlTemp()
        self.controlPressure = ControlPressure()
        self.controlPoll = ControlPoll()

        self.logger = Logger()

        self.graphs.addTab(self.controlTemp, 'Temperature')
        self.graphs.addTab(self.controlPressure, 'Pressure')
        self.graphs.addTab(self.controlPoll, 'Air quality')

        self.addTab(self.graphs, 'Graphs')
        self.addTab(self.logger, 'Debug')

class TableItem(QtGui.QTableWidgetItem):
    def __init__(self, parent, text, graph=None, u=0, colour=None):
        super(TableItem, self).__init__()
        self.setFlags(QtCore.Qt.NoItemFlags)

        if colour == None:
            colour = QtGui.QBrush((QtGui.QColor(graph.colour)))
        else:
            colour = QtGui.QBrush((QtGui.QColor(colour)))

        self.colour = colour
        self.setForeground(self.colour)

        self.parent  = parent
        self.text = text
        self.graph = graph

        if u == 1:
            self.setText('...')
            Timing.timer.timeout.connect(self.update)
        else:
            self.setText(text)

    def update(self):
        text = eval(self.text)
        try:
            text = float(text)
        except ValueError:
            pass
        if type(text) == float:
            text = '%.3f' %(text) #np
        self.setText(unicode(text))
        self.parent.resizeColumnToContents(2)

class CurrentData(QtGui.QTableWidget):
    def __init__(self, graphs):
        super(CurrentData, self).__init__()
        self.setRowCount(6)
        self.setColumnCount(3)
        self.setMaximumWidth(280)
        self.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setVisible(False)

        self.timer = QtCore.QTimer()
        self.timer.start(100)

        self.setItem(0, 0, TableItem(self, '  Temperature', graphs[0]))
        self.setItem(0, 1, TableItem(self, 'self.graph.data[0]', graphs[0], 1))
        self.setItem(0, 2, TableItem(self, 'self.graph.data[1]', graphs[0], 1))
        self.setItem(1, 0, TableItem(self, '  Pressure', graphs[1]))
        self.setItem(1, 1, TableItem(self, 'self.graph.data[0]', graphs[1], 1))
        self.setItem(1, 2, TableItem(self, 'self.graph.data[1]', graphs[1], 1))
        self.setItem(2, 0, TableItem(self, '  Air quality', graphs[2]))
        self.setItem(2, 1, TableItem(self, 'self.graph.data[0]', graphs[2], 1))
        self.setItem(2, 2, TableItem(self, 'self.graph.data[1]', graphs[2], 1))
        self.setItem(3, 0, TableItem(self, '  Altitude', colour='#ff00ff'))
        self.setItem(3, 1, TableItem(self, 'hypsometricFormula(101325.0)', graphs[0], 1, colour='#ff00ff'))
        self.setItem(3, 2, TableItem(self, 'm', colour='#ff00ff'))
        self.setItem(4, 0, TableItem(self, '  ----', colour='#ffffff'))
        self.setItem(4, 1, TableItem(self, '----', colour='#ffffff'))
        self.setItem(4, 2, TableItem(self, '----', colour='#ffffff'))
        self.setItem(5, 0, TableItem(self, '  Mean T.', graphs[0]))
        self.setItem(5, 1, TableItem(self, 'self.graph.mean', graphs[0], 1))
        self.setItem(5, 2, TableItem(self, 'self.graph.data[1]', graphs[0], 1))

class DataLayout(QtGui.QGridLayout):
    def __init__(self, graphs):
        super(DataLayout, self).__init__()
        self.setSpacing(1)
        self.setContentsMargins(0, 0, 0, 0)

        self.data = CurrentData(graphs)
        self.controlFrame = ControlFrame()

        self.addWidget(self.data, 0, 0)
        self.addWidget(self.controlFrame, 0, 1)

class DataFrame(QtGui.QWidget):
    def __init__(self, graphs):
        super(DataFrame, self).__init__()
        self.dataLayout = DataLayout(graphs)
        self.setLayout(self.dataLayout)

class PlottingLayout(QtGui.QGridLayout):
    def __init__(self):
        super(PlottingLayout, self).__init__()
        self.setSpacing(1)
        self.setContentsMargins(0, 0, 0, 0)

        self.sqlite = SQLite()

        Timing.timer.start(100)
        Timing.slowTimer.start(1000)
        Timing.passiveTimer.start(3000)

        # Graphs
        self.tempGraph = TempGraph(self)
        self.pressureGraph = PressureGraph(self)
        self.pollGraph = PollGraph(self)

        self.dataFrame = DataFrame([self.tempGraph, self.pressureGraph, self.pollGraph])

        self.addWidget(self.tempGraph, 0, 0)
        self.addWidget(self.pressureGraph, 0, 1)
        self.addWidget(self.pollGraph, 1, 0)
        self.addWidget(self.dataFrame, 1, 1)

        self.startTimerTemp = QtCore.QTimer.singleShot(1000, self.tempGraph.start)
        self.startTimerPress = QtCore.QTimer.singleShot(1000, self.pressureGraph.start)
        self.startTimerPoll = QtCore.QTimer.singleShot(1000, self.pollGraph.start)
        Timing.slowTimer.timeout.connect(self.sqliteRecord)

    def sqliteRecord(self):
        self.sqlite.addRecords()

class PlottingFrame(QtGui.QWidget):
    def __init__(self):
        super(PlottingFrame, self).__init__()
        self.plottingLayout = PlottingLayout()
        self.setLayout(self.plottingLayout)

class MainLayout(QtGui.QGridLayout):
    def __init__(self):
        super(MainLayout, self).__init__()
        self.setSpacing(1)
        self.setContentsMargins(0, 0, 0, 0)

        self.topBar = TopBar()
        self.plottingFrame = PlottingFrame()

        self.addWidget(self.topBar, 0, 0)
        self.addWidget(self.plottingFrame, 1, 0)

class MainFrame(QtGui.QWidget):
    def __init__(self):
        super(MainFrame, self).__init__()
        self.mainLayout = MainLayout()
        self.setLayout(self.mainLayout)

class MainWindow(QtGui.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.move(100, 100)
        self.setWindowTitle('8SpaceDataProcessor V.%s' %VERSION)
        self.mainWidget = MainFrame()
        self.setCentralWidget(self.mainWidget)
        self.setStyleSheet(open('css\default.css', 'r').read())
        self.showMaximized()
        self.show()

if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    app.setStyle(QtGui.QStyleFactory.create('Fusion'))
    app.setApplicationName('8SpaceDataProcessor V.%s' %VERSION)

    window = MainWindow()
    sys.exit(app.exec_())
