# Makefile for Single Client-Server Socket Communication

CXX = g++
CXXFLAGS = -Wall -std=c++11
TARGET_SERVER = server
TARGET_CLIENT = client
SOURCE_SERVER = server.cpp
SOURCE_CLIENT = client.cpp

all: $(TARGET_SERVER) $(TARGET_CLIENT)

build: $(TARGET_SERVER) $(TARGET_CLIENT)

$(TARGET_SERVER): $(SOURCE_SERVER)
	$(CXX) $(CXXFLAGS) -o $(TARGET_SERVER) $(SOURCE_SERVER)

$(TARGET_CLIENT): $(SOURCE_CLIENT)
	$(CXX) $(CXXFLAGS) -o $(TARGET_CLIENT) $(SOURCE_CLIENT)

clean:
	rm -f $(TARGET_SERVER) $(TARGET_CLIENT)

run:
	./server & \
	SERVER_PID=$$!; \
	sleep 1; \
	./client; \
	kill $$SERVER_PID



.PHONY: all clean run-server run-client