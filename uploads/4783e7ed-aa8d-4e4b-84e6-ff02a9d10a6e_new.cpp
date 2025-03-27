#include <iostream>
#include <vector>
using namespace std;
int main(){
    int n;
    cin>>n;
    vector<int> a;
    for(int i=0;i<n;i++){
        int x;
        cin>>x;
        if(!a.size()){
            a.push_back(x);
        }
        else{
            if(x >= a.back()){
                a.push_back(x);
            }
            else{
                auto it = upper_bound(a.begin(), a.end(), x);
                *it = x;
            }
        }
    }
    cout<<a.size()<<endl;
    return 0;
}