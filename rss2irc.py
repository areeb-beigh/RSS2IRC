# -*- coding: utf-8 -*-

# Python RSS2IRC Bot - github.com/areebbeigh/rss2irc

##############################################################################
#                                                                            #
#    Copyright (C) 2016  Areeb Beigh <areebbeigh@gmail.com>                  #
#                                                                            #
#    This program is free software: you can redistribute it and/or modify    #
#    it under the terms of the GNU General Public License as published by    #
#    the Free Software Foundation, either version 3 of the License, or       #
#    (at your option) any later version.                                     #
#                                                                            #
#    This program is distributed in the hope that it will be useful,         #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of          #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the           #
#    GNU General Public License for more details.                            #
#                                                                            #
#    You should have received a copy of the GNU General Public License       #
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.   #
#                                                                            #
##############################################################################

# :Areeb!Areeb@oper.irchound.tk PRIVMSG #lobby :!credits
# Above is a reference to how the bot sees messages, you'll need to understand this if you want to add custom commands

# TODO: Add !pausefeeds and !resumefeeds

# Python imports
import feedparser  # pip install feedparser
import socket
import time
import re
from threading import Timer

# Configuration import
from config.config import *

BOT_VERSION = "v2.2"

def main():
    global irc, feed_manager, ALT_NICK
    print("""
    ---------------------------------------------
    RSS2IRC Bot by Areeb - github.com/areebbeigh
    ---------------------------------------------
    """)
    # Validating configuration
    for channel in CHANNELS:
        if channel[0] != '#':
            CHANNELS[CHANNELS.index(channel)] = '#' + channel
    if ALT_NICK == NICK:
        ALT_NICK += "_"
    irc = IRCBot()
    feed_manager = Feed()
    update()
    irc.connect()


class IRCBot:
    """ All the IRC aspects of the bot are managed in this class """

    def __init__(self):
        self.s = socket.socket()
        self.new_feed = False
        self.current_nick = NICK  # the bot's current nick name
        self.joined_channels = set()  # channels the bot joined
        self.kicked_channels = set()  # channesl the bot was kicked out of

    def connect(self):
        """ Connects the bot to the IRC network """
        self.s.connect((str(NET), int(PORT)))
        self.s.send(bytes("NICK %s\r\n" % NICK, "UTF-8"))
        self.s.send(bytes("USER %s %s bla :%s\r\n" % (IDENT, NET, REALNAME), "UTF-8"))
        time.sleep(10)
        self.identify()
        self.join_all_channels()
        last_check = time.time()
        first_time = True
        while True:
            read_buffer = "" + self.s.recv(1024).decode("UTF-8")
            temp = read_buffer.split("\n")
            read_buffer = temp.pop()
            print(read_buffer)

            if first_time:
                self.join_all_channels()
                first_time = False

            for line in temp:
                line = str.rstrip(line)
                line = str.split(line)
                print(line)
                if len(line) >= 2 and line[1] == '433':
                    # 433 is an error code - ERR_NICKNAMEINUSE i.e the nickname is already in use
                    print("Nick already exists, changing nick to " + ALT_NICK)
                    self.change_nick(ALT_NICK)
                    self.join_all_channels()

                ########################### CTCP replies start here ###########################

                if line[0] == 'PING':
                    self.s.send(bytes('PONG ' + line[1] + '\r\n', 'UTF-8'))
                    print("Responded to PING")

                if len(line) >= 4 and line[2] == self.current_nick:
                    user = self.get_user(line[0])
                    command = line[3]
                    ctcp = ""

                    if command == ":\x01VERSION\x01":
                        self.send_command_NOTICE(user, "VERSION RSS2IRC Bot %s by Areeb" % BOT_VERSION)
                        ctcp = "VERSION"
                    if command == ":\x01TIME\x01":
                        self.send_command_NOTICE(user, "TIME Buy a watch!")
                        ctcp = "TIME"
                    if command == ":\x01PING\x01":
                        self.send_command_NOTICE(user, "PONG")
                        ctcp = "PING"

                    if ctcp:
                        print("Responded to " + ctcp)

                ############################ CTCP replies end here ############################

                if len(line) >= 2 and line[1] in ["KICK", "JOIN"]:
                    update = False

                    if line[1] == "KICK":
                        update = True
                        if self.current_nick == line[3]:
                            chan = line[2]
                            if chan[0] == ":":
                                chan = chan[1:]
                            print("Kicked from " + chan)
                            self.kicked_channels.add(chan)
                            if chan in self.joined_channels:
                                self.joined_channels.remove(chan)
                            if chan in CHANNELS:
                                self.join_channel(chan)

                    if line[1] == "JOIN":
                        update = True
                        if self.is_own_action(line[0]):
                            chan = line[2]
                            if chan[0] == ":":
                                chan = chan[1:]
                            print("Joined channel " + chan)
                            self.joined_channels.add(chan)
                            if chan in self.kicked_channels:
                                self.kicked_channels.remove(chan)

                    if update:
                        print("Joined to:", self.joined_channels)
                        print("Kicked from:", self.kicked_channels)

            # Check regularly if the bot has been disconnected from any of the channels
            # this will start 1 minute after the bot connects to avoid spam.
            if time.time() - last_check > 15:
                # print(self.joined_channels, self.kicked_channels)
                for chan in CHANNELS:
                    if chan not in self.joined_channels:
                        print("[Channel Check] Joining " + chan)
                        self.join_channel(chan)
                    last_check = time.time()

            if self.new_feed:
                self.broadcast(feed_manager.feed_data[len(feed_manager.feed_data) - 1])
                self.new_feed = False

            '''
            if line[0] == 'PING':
                print("Responded to PING")
                self.s.send(bytes('PONG ' + line[1] + '\r\n', 'UTF-8'))
            '''

            # Responses to different commands start here
            if len(line) >= 3 and line[2] in CHANNELS:
                chan = line[2]
                if len(line) == 4 and line[2] in CHANNELS and line[3] == ':!killsocket' and line[0] == ADMIN:
                    print("!killsocket by " + ADMIN)
                    self.s.close()
                    exit()
                if len(line) == 4 and line[2] in CHANNELS and line[3] == ':!login' and line[0] == ADMIN:
                    self.identify()
                if len(line) == 4 and line[2] in CHANNELS and line[3] == ':!feed':
                    self.msg(chan, "3Last three feeds:")
                    for feed in feed_manager.last_feed(3):
                        self.msg(chan, feed)

                if len(line) == 6 and line[2] in CHANNELS and line[3] == ':!feed' and line[4] == 'last':
                    try:
                        for feed in feed_manager.last_feed(int(line[5])):
                            self.msg(chan, feed)
                    except ValueError:
                        self.msg(chan, 'Error: Invalid parameters')

                if len(line) == 5 and line[2] in CHANNELS and line[3] == ':!feed' and line[4] == 'list':
                    self.msg(chan, '3Feed list:')
                    for feed_resource in feed_resources:
                        self.msg(chan, feed_resource)

                if len(line) == 5 and line[2] in CHANNELS and line[3] == ':!feed' and line[4] == 'help':
                    self.msg(chan, '3Commands:')
                    self.msg(chan, '4!feed             -   13Returns last 3 feed_manager')
                    self.msg(chan, '4!feed help        -   13View this help dialogue')
                    self.msg(chan, '4!feed last (1-5)  -   13Returns last \'n\' number of feed_manager')
                    self.msg(chan, '4!feed list        -   13Returns the feed resources currently being used')
                    self.msg(chan, '4!credits          -   13View bot credits')

                if len(line) == 4 and line[2] in CHANNELS and line[3] == ':!credits':
                    # Don't remove please :)
                    self.msg(chan, '3Python RSS2IRC Bot %s Credits' % BOT_VERSION)
                    self.msg(chan, "4RSS2IRC v2.2 by Areeb - 12 https://github.com/areebbeigh/RSS2IRC")

    def send_command_NOTICE(self, user, command):
        """ Send PRIVMSG to user """
        print("NOTICE to " + user + ":", command)
        self.s.send(bytes("NOTICE " + user + " :\x01" + command + "\x01\r\n", "UTF-8"))

    def get_user(self, line):
        """ Returns the user nickname """
        return line.strip(":").split("!")[0]

    def is_own_action(self, user_info):
        """ Determines whether the action was related to this bot """
        if re.search(self.current_nick, user_info):
            return True
        return False

    def identify(self):
        """ Logs in with NickServ """
        print("Attempting to identify...")
        print(bytes('PRIVMSG NickServ :IDENTIFY %s %s\r\n' % (NICK, PASSWORD), 'UTF-8'))
        self.s.send(bytes('PRIVMSG NickServ :IDENTIFY %s %s\r\n' % (NICK, PASSWORD), 'UTF-8'))

    def change_nick(self, new_nick):
        """ Changes the bots nickname to new_nick """
        self.s.send(bytes("NICK %s\r\n" % new_nick, "UTF-8"))
        self.current_nick = new_nick

    def join_all_channels(self):
        """ Joins all the channels in CHANNELS """
        for chan in CHANNELS:
            self.join_channel(chan)

    def join_channel(self, channel):
        """ Joins the bot to the given channel """
        self.s.send(bytes('JOIN ' + channel + '\r\n', 'UTF-8'))
        self.msg(channel, "%s Now Online - Checking latest feed - !feed help to view commands" % NICK)
        for feed_msg in feed_manager.last_feed(1):
            self.msg(channel, feed_msg)

    def msg(self, channel, msg):
        """ Sends the given to the given channel """
        self.s.send(bytes('PRIVMSG ' + str(channel) + ' :' + str(msg) + '\r\n', 'UTF-8'))

    def broadcast(self, msg):
        """ Sends a message to all the channels in the CHANNELS list """
        for channel in CHANNELS:
            self.msg(channel, msg)


class Feed:
    """ All the feed aspects of the bot are managed here """

    def __init__(self):
        self.feed_data = []

    def feed_refresh(self):
        """ Refreshes the feed data """
        first_time = False
        if len(self.feed_data) == 0:
            first_time = True
        for feed_resource in feed_resources:
            f = feedparser.parse(feed_resource)
            for entry in f.entries:
                feed = "4" + entry.title + " | " + "12" + entry.link
                if feed not in self.feed_data:
                    if not first_time:
                        irc.new_feed = True
                    self.feed_data.append(feed)

    def last_feed(self, n=1):
        """
        Returns a list of the latest 'n' feed(s).
        """
        MAX_FEEDS = 5  # Maximum number of feeds a user can request
        msgs = []
        if n > MAX_FEEDS or n < 1:
            return ["Error: Can send only maximum %s feed_manager and minimum 1" % MAX_FEEDS]
        else:
            self.feed_refresh()
            for i in range(n):
                try:
                    msgs.append(self.feed_data[i])
                except IndexError:
                    msgs.append("No more feeds")
                    break
            return msgs


def update():
    """ Checks for feeds every 'n' seconds (edit REFRESH_RATE variable above) """
    x = Timer(REFRESH_RATE, update)
    x.daemon = True
    x.start()
    feed_manager.feed_refresh()


if __name__ == "__main__":
    main()
