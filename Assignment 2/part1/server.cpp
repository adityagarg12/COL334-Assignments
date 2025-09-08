#include <iostream>
#include <string>
#include <fstream>
#include <sstream>
#include <vector>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

using namespace std;

bool quiet_mode = false;

struct Config {
    string server_ip;
    int server_port;
    int k;
    int p;
    string filename;
};

vector<string> words; 


Config LoadConfig(const string& configFile) {
    Config config;
    ifstream file(configFile);
    if (!file.is_open()) {
        cerr << "Failed to open config file: " << configFile << endl;
        exit(1);
    }
    
    string line;
    while (getline(file, line)) {
      
        size_t start = line.find_first_not_of(" \t");
        if (start == string::npos) continue;
        line = line.substr(start);
        
        if (line.find("\"server_ip\"") != string::npos) {
            size_t colonPos = line.find(":");
            size_t quoteStart = line.find("\"", colonPos);
            size_t quoteEnd = line.find("\"", quoteStart + 1);
            config.server_ip = line.substr(quoteStart + 1, quoteEnd - quoteStart - 1);
        }
        else if (line.find("\"server_port\"") != string::npos) {
            size_t colonPos = line.find(":");
            string numStr = line.substr(colonPos + 1);
            string cleanNum = "";
            for (char c : numStr) {
                if (isdigit(c)) cleanNum += c;
            }
            config.server_port = stoi(cleanNum);
        }
        else if (line.find("\"filename\"") != string::npos) {
            size_t colonPos = line.find(":");
            size_t quoteStart = line.find("\"", colonPos);
            size_t quoteEnd = line.find("\"", quoteStart + 1);
            config.filename = line.substr(quoteStart + 1, quoteEnd - quoteStart - 1);
        }
    }
    
    file.close();
    return config;
}

void LoadWordsFromFile(const string& filename) {
    ifstream file(filename);
    string content;
    if (file.is_open()) {
        getline(file, content); 
        file.close();
    
        stringstream ss(content);
        string word;
        while (getline(ss, word, ',')) {
           
            if (!word.empty() && word.back() == '\r') {
                word.pop_back();
            }
            words.push_back(word);
        }
             
       if(!quiet_mode) cout << "Loaded " << words.size() << " words from " << filename << endl;
    } else {
        cout << "Failed to open file: " << filename << endl;
    }
}

string ProcessRequest(const string& request, int& requestCount) {
    requestCount++;

    if(!quiet_mode){
        cout << "\nProcessing Request #" << requestCount<< endl;
        cout << "Received request: " << request << endl;
    }
    
    size_t commaPos = request.find(',');
    if (commaPos == string::npos) {
        cout << "Invalid request format" << endl;
        return "Invalid request format\n";
    }
    
    try {
        int p = stoi(request.substr(0, commaPos));
        string secondPart = request.substr(commaPos + 1);
        
      
        if (secondPart.back() == '\n') {
            secondPart.pop_back();
        }
        
        int k = stoi(secondPart); 

        if(!quiet_mode) cout << "Parsed request: offset=" << p << ", count=" << k << endl;
        
        string response;
        
        
        if (p >= (int)words.size()) {
            if(!quiet_mode) cout << "Offset " << p << " is beyond file size (" << words.size() << ") - sending EOF" << endl;
            response = "EOF\n";
        } else {
          
            int wordsToSend = min(k, (int)words.size() - p);
            bool reachedEOF = (p + k > (int)words.size());
            
            cout << endl;
            
            for (int i = 0; i < wordsToSend; i++) {
                if (i > 0) response += ",";
                response += words[p + i];
            }
            
            if (reachedEOF) {
                response += ",EOF";
            }
            
            response += "\n";
        }

        if(!quiet_mode) cout << "Sending response: " << response;
        return response;
        
    } catch (const exception& e) {
        cout << "ERROR: Exception while processing request: " << e.what() << endl;
        return "Invalid request format\n";
    }
}

int main(int argc, char* argv[]) {
   
    string configFile = "config.json";
    for (int i = 1; i < argc - 1; ++i) {
        if (string(argv[i]) == "--config") {
            configFile = argv[i + 1];
            break;
        }
    }

    for (int i = 1; i < argc; ++i) {
        if (string(argv[i]) == "--quiet") {
            quiet_mode = true;
            break;
        }
    }

    Config config = LoadConfig(configFile);

    if(!quiet_mode) {
        cout << "Server Configuration:" << endl;
        cout << "IP: " << config.server_ip << endl;
        cout << "Port: " << config.server_port << endl;
        cout << "Filename: " << config.filename << endl << endl;
    }

   
    LoadWordsFromFile(config.filename);
    
  
    int sockfd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sockfd < 0) {
        cerr << "Socket creation failed" << endl;
        return 1;
    }
    
    cout << "Socket created successfully " << sockfd << endl;
    
    
    int nOptVal = 1;
    int nOptLen = sizeof(nOptVal);
    int nRet = setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, (const char*)&nOptVal, nOptLen);
    if (nRet < 0) {
        cerr << "setsockopt(SO_REUSEADDR) failed" << endl;
        close(sockfd);
        return 1;
    }
    
    cout << "setsockopt(SO_REUSEADDR) successful" << endl;
    
  
    struct sockaddr_in srv;
    srv.sin_family = AF_INET;
    if (config.server_ip == "INADDR_ANY" || config.server_ip.empty()) {
        srv.sin_addr.s_addr = INADDR_ANY;
    } else {
        srv.sin_addr.s_addr = inet_addr(config.server_ip.c_str());
    }
    srv.sin_port = htons(config.server_port);
    memset(&(srv.sin_zero), 0, 8);
    
    
    nRet = bind(sockfd, (sockaddr*)&srv, sizeof(sockaddr));
    if (nRet < 0) {
        cerr << "Socket bind failed" << endl;
        close(sockfd);
        return 1;
    }
    
    cout << "Socket bind successful" << endl;
    
   
    nRet = listen(sockfd, 1); 
    if (nRet < 0) {
        cerr << "Listen failed" << endl;
        close(sockfd);
        return 1;
    }
    
    cout << "Server listening on " << config.server_ip << ":" << config.server_port << endl;
   
  
    socklen_t nLen = sizeof(struct sockaddr);
    int clientSocket = accept(sockfd, NULL, &nLen);
    if (clientSocket < 0) {
        cerr << "Accept failed" << endl;
        close(sockfd);
        return 1;
    }
    
    cout << "Client connected successfully on socket: " << clientSocket << endl;
   
    
  
    char buffer[256];
    int requestCount = 0;
    
    while (true) {
        memset(buffer, 0, sizeof(buffer));
        int bytesReceived = recv(clientSocket, buffer, sizeof(buffer) - 1, 0);
        
        if (bytesReceived <= 0) {
            cout << "\nClient disconnected or error occurred" << endl;
            break;
        }
        
        buffer[bytesReceived] = '\0';
        string request(buffer);
        
       
        string response = ProcessRequest(request, requestCount);
        
        
        int bytesSent = send(clientSocket, response.c_str(), response.length(), 0);
        if (bytesSent < 0) {
            cout << "Failed to send response to client" << endl;
            break;
        }

    }
    
 
    close(clientSocket);
    close(sockfd);
    cout << "Server shutting down..." << endl;
    
    return 0;
}