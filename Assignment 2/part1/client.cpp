#include <iostream>
#include <string>
#include <fstream>
#include <sstream>
#include <vector>
#include <map>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <chrono>

using namespace std;

bool quiet_mode = false;

struct Config {
    string server_ip;
    int server_port;
    int k;
    int p;
    string filename;
};

// config file se info extract
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
        else if (line.find("\"k\"") != string::npos) {
            size_t colonPos = line.find(":");
            string numStr = line.substr(colonPos + 1);
            string cleanNum = "";
            for (char c : numStr) {
                if (isdigit(c)) cleanNum += c;
            }
            config.k = stoi(cleanNum);
        }
        else if (line.find("\"p\"") != string::npos) {
            size_t colonPos = line.find(":");
            string numStr = line.substr(colonPos + 1);
            string cleanNum = "";
            for (char c : numStr) {
                if (isdigit(c)) cleanNum += c;
            }
            config.p = stoi(cleanNum);
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

vector<string> ParseResponse(const string& response) {
    vector<string> words;
    stringstream ss(response);
    string word;
    while (getline(ss, word, ',')) {
        if (!word.empty() && word != "EOF" && word != "EOF\n" && word != "EOF\r" && word != "\n" && word != "\r") {
            
            if (word.back() == '\n' || word.back() == '\r') {
                word.pop_back();
            }

            words.push_back(word);
        }
    }
    return words;
}

// frequency print
void DisplayWordFrequencies(const map<string, int>& wordFrequency) {
    cout << "\nFinal Word Frequencies" << endl;
    if (wordFrequency.empty()) {
        cout << "No words received." << endl;
    } else {
        for (const auto& pair : wordFrequency) {
            cout << pair.first << ", " << pair.second << endl;
        }
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

    //to not print debug statements
    for (int i = 1; i < argc; ++i) {
        if (string(argv[i]) == "--quiet") {
            quiet_mode = true;
            break;
        }
    }
    
    Config config = LoadConfig(configFile);
    
    if(!quiet_mode){
        cout << "Client Configuration:" << endl;
        cout << "Server IP: " << config.server_ip << endl;
        cout << "Server Port: " << config.server_port << endl;
        cout << "Initial Request: p=" << config.p << ", k=" << config.k << endl;
        cout << "File: " << config.filename << endl << endl;
    }
    // Create socket
    int nClientSocket = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (nClientSocket < 0) {
        cerr << "Socket creation failed" << endl;
        return 1;
    }
    
    cout << "Socket created successfully" << endl;
    
    struct sockaddr_in srv;
    srv.sin_family = AF_INET;
    srv.sin_addr.s_addr = inet_addr(config.server_ip.c_str());
    srv.sin_port = htons(config.server_port);
    memset(&(srv.sin_zero), 0, 8);
    
    
    int nRet = connect(nClientSocket, (struct sockaddr*)&srv, sizeof(srv));
    if (nRet < 0) {
        cerr << "Connection to server failed" << endl;
        close(nClientSocket);
        return 1;
    }
    
    cout << "Connected to server successfully!" << endl;
    
    
    auto start_time = std::chrono::high_resolution_clock::now();
    
   
    int current_offset = config.p;
    int request_count = 0;
    bool eof_reached = false;
    map<string, int> totalWordFrequency;
    int total_words_received = 0;
        
    
    while (!eof_reached) {
        request_count++;
        
        // request format -> format "p,k\n"
        string request = to_string(current_offset) + "," + to_string(config.k) + "\n";

        if (!quiet_mode) {
            cout << "\n Request #" << request_count<< endl;
            cout << "Sending request: offset=" << current_offset << ", count=" << config.k << endl;
        }

        int bytes_sent = send(nClientSocket, request.c_str(), request.length(), 0);

        if (bytes_sent < 0) {
            cerr << "Failed to send request" << endl;
            break;
        }
        
       
        char buffer[1024] = {0};
        int bytesReceived = recv(nClientSocket, buffer, sizeof(buffer) - 1, 0);
        if (bytesReceived <= 0) {
            cout << "No data received or connection closed." << endl;
            break;
        }
        
        buffer[bytesReceived] = '\0';
        string response(buffer);

        if (!quiet_mode) {
            cout << "Received response: " << response;
        }

      
        if (response == "EOF\n") {
            
            if(!quiet_mode){
                cout << "EOF reached" << endl;
            } 
            eof_reached = true;
        } 
        else if (response.find("EOF") != string::npos) {
            if(!quiet_mode){
                cout << "EOF found in response " << endl;
            }
            eof_reached = true;
            
            
            vector<string> words = ParseResponse(response);

             //frequency update for words
            for (const string& word : words) {

                if(!quiet_mode) cout << word << " ";
               
                totalWordFrequency[word]++;
                total_words_received++;
            }
            cout << endl;
        } 
        else {

            vector<string> words = ParseResponse(response);
            
            for (const string& word : words) {
                if(!quiet_mode) cout << word << " " ;

                totalWordFrequency[word]++;
                total_words_received++;
            }
            if(!quiet_mode) {
                cout << endl;
            }

           
            current_offset += words.size();
        }
        
    }
    
   
    auto end_time = std::chrono::high_resolution_clock::now();
    
    std::chrono::duration<double, std::milli> elapsed = end_time - start_time;
    
    
    if(!quiet_mode) cout << "Total words received: " << total_words_received << endl;
    
  
    DisplayWordFrequencies(totalWordFrequency);
    
    cout << "ELAPSED_MS:" << elapsed.count() << endl;
    
   
    close(nClientSocket);
    cout << "\nConnection closed." << endl;
    
    return 0;
}